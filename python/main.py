
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from tqdm import tqdm

import aiohttp
import os
import re
import requests

executor = ThreadPoolExecutor()

dnlds = []

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

def get_filename_from_request(response : aiohttp.ClientResponse, file_id : str) -> Optional[str]:
	content_disposition = response.headers.get('Content-Disposition', '')
	if 'filename=' in content_disposition:
		filename_match = re.search(r'filename="(.+?)"', content_disposition)
		if filename_match:
			return filename_match.group(1)
	return file_id

def download_in_executor(url, params, directory, file_id, chunk_size):
	with requests.Session() as client:
		response = client.get(url, params=params, stream=True)
		response.raise_for_status()
		content_disposition = response.headers.get('Content-Disposition', '')
		print(content_disposition)
		# Assuming `get_filename_from_request` generates a filename
		filename = get_filename_from_request(response, file_id)
		filepath = os.path.join(directory, filename)
		total_size = int(response.headers.get('Content-Length', 0))
		if os.path.exists(filepath):
			existing_size = os.path.getsize(filepath)
			if existing_size == total_size:
				print(f"File already downloaded: {filepath}")
				return filepath
			else:
				print(f"File exists but size does not match. Expected: {total_size}, Found: {existing_size}")
				os.remove(filepath)
		progress_bar = tqdm(total=total_size, unit='B', unit_scale=True, desc=os.path.basename(filepath))
		with open(filepath, 'wb') as file:
			for chunk in response.iter_content(chunk_size=chunk_size):
				if chunk:
					file.write(chunk)
					progress_bar.update(len(chunk))
		progress_bar.close()
		return filepath

async def download_file(url, params, directory, file_id, chunk_size=512):
	loop = asyncio.get_event_loop()
	executor = ThreadPoolExecutor()
	return await loop.run_in_executor(executor, download_in_executor, url, params, directory, file_id, chunk_size)

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
				url = "https://drive.usercontent.google.com/download?export=download"
				params = {'id': file_id, 'confirm' : 't'}
				await download_file(url, params, directory, file_id, chunk_size=chunk_size)
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
	asyncio.run(bulk_download_files(links, directory, simultaneous=1, chunk_size=512))

	print(dnlds)
