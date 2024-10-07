
from typing import Optional
from tqdm import tqdm

import aiohttp
import os
import re

async def download_file(url : str, filepath : str, chunk_size : int = 512) -> None:
	async with aiohttp.ClientSession(headers=HEADERS) as session:
		response : aiohttp.ClientResponse = await session.get(url, allow_redirects=True)
		response.raise_for_status()
		total_size = int(response.headers.get('Content-Length', 0))
		progress_bar = tqdm(total=total_size, unit='B', unit_scale=True, desc=os.path.basename(filepath))
		with open(filepath, 'wb') as file:
			async for chunk in response.content.iter_chunked(chunk_size):
				if chunk:
					file.write(chunk)
					progress_bar.update(len(chunk))
		progress_bar.close()

async def extract_file_id(drive_url: str) -> Optional[str]:
	regex_patterns = [
		r'https?://drive\.google\.com/file/d/([a-zA-Z0-9_-]+)/?',
		r'https?://drive\.google\.com/uc\?id=([a-zA-Z0-9_-]+)',
		r'https?://drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)'
	]
	for pattern in regex_patterns:
		match = re.search(pattern, drive_url)
		if match:
			return match.group(1)
	return None

async def get_filename_from_request(response : aiohttp.ClientResponse, file_id : str) -> Optional[str]:
	content_disposition = response.headers.get('Content-Disposition', '')
	if 'filename=' in content_disposition:
		filename_match = re.search(r'filename="(.+?)"', content_disposition)
		if filename_match:
			return filename_match.group(1)
	return file_id

async def download_google_drive_file(file_id: str, directory: str, chunk_size: int = 512) -> None:
	url = "https://drive.usercontent.google.com/download?export=download"
	params = {'id': file_id, 'confirm' : 't'}
	async with aiohttp.ClientSession() as client:
		async with client.get(url, params=params) as response:
			response.raise_for_status()
			print(response.headers['Content-Disposition'])
			filename : str = await get_filename_from_request(response, file_id)
			filepath = os.path.join(directory, filename)
			total_size = int(response.headers.get('Content-Length', 0))
			if os.path.exists(filepath):
				existing_size = os.path.getsize(filepath)
				if existing_size == total_size:
					print(f"File already downloaded: {filepath}")
					return
				else:
					print(f"File exists but size does not match. Expected: {total_size}, Found: {existing_size}")
					os.remove(filepath)
			progress_bar = tqdm(total=total_size, unit='B', unit_scale=True, desc=os.path.basename(filepath))
			with open(filepath, 'wb') as file:
				async for chunk in response.content.iter_chunked(chunk_size):
					if chunk:
						file.write(chunk)
						progress_bar.update(len(chunk))
			progress_bar.close()

async def bulk_download_files(file_ids : list[str], directory : str, simultaneous : int = 3, chunk_size : int = 512) -> None:
	os.makedirs(directory, exist_ok=True)
	semaphore = asyncio.Semaphore(simultaneous)
	async def sem_download(url):
		nonlocal chunk_size, directory
		async with semaphore:
			print(f'Starting download: {url}')
			try:
				file_id : str = await extract_file_id(url)
				if file_id is None:
					raise ValueError("Could not extract file_id from the url.")
				await download_google_drive_file(file_id, directory, chunk_size=chunk_size)
				success = True
				print(f'Successful download: {url}')
			except Exception as e:
				print(f'Failed to download: {url}')
				print(e)
				success = False
			return success
	tasks = [sem_download(url) for url in file_ids]
	print(f'Starting bulk download of {len(file_ids)} items.')
	results = await asyncio.gather(*tasks)
	print(f'Finished bulk download of {len(file_ids)} items.')
	return results

def get_links_from_file(filepath : str) -> list[str]:
	url_pattern = re.compile(r'https?://[^\s]+')
	links = []
	with open(filepath, 'r', encoding='utf-8') as file:
		for line in file.readlines():
			links.extend(url_pattern.findall(line))
	return [item for item in links if item is not None]

if __name__ == '__main__':
	import asyncio

	links : list[str] = get_links_from_file('bookmarks.html')
	links : list[str] = [item for item in links if "drive.google.com" in item]

	directory = 'downloads'
	asyncio.run(bulk_download_files(links, directory, simultaneous=3, chunk_size=512))
