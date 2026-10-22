"""
KIE.AI Nano Banana API client
"""

import aiohttp
import asyncio
import logging
import json
from typing import Optional, Dict, Any, List
from config import (
    KIE_API_KEY,
    KIE_API_URL,
    POLLING_INTERVAL,
    POLLING_MAX_ATTEMPTS,
    MODEL_GENERATE,
    MODEL_EDIT,
)

_logger = logging.getLogger(__name__)


class NanoBananaAPIError(Exception):
    """Custom exception for Nano Banana API errors"""
    pass


class NanoBananaClient:
    """Client for KIE.AI Nano Banana API"""

    def __init__(self):
        self.base_url = KIE_API_URL
        self.api_key = KIE_API_KEY
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def create_task(
        self,
        prompt: str,
        mode: str = "generate",
        image_urls: Optional[List[str]] = None,
        output_format: str = "png",
        image_size: str = "1:1",
        callback_url: Optional[str] = None,
    ) -> str:
        """
        Create a new image generation/editing task.

        Args:
            prompt: Text prompt for generation or editing instructions
            mode: "generate" or "edit"
            image_urls: List of image URLs (required for edit mode)
            output_format: "png" or "jpeg"
            image_size: Aspect ratio (e.g., "1:1", "16:9", etc.)
            callback_url: Optional callback URL for task completion notifications

        Returns:
            task_id: Task ID for polling status

        Raises:
            NanoBananaAPIError: If API request fails
        """
        # Select model based on mode
        model = MODEL_GENERATE if mode == "generate" else MODEL_EDIT

        # Build request payload
        payload: Dict[str, Any] = {
            "model": model,
            "input": {
                "prompt": prompt,
                "output_format": output_format,
                "image_size": image_size,
            }
        }

        # Add image_urls for edit mode
        if mode == "edit":
            if not image_urls:
                raise NanoBananaAPIError("image_urls required for edit mode")
            payload["input"]["image_urls"] = image_urls

        # Add callback URL if provided
        if callback_url:
            payload["callBackUrl"] = callback_url

        # Make API request
        url = f"{self.base_url}/api/v1/jobs/createTask"
        _logger.info(f"Creating task with model={model}, mode={mode}")
        _logger.info(f"Payload: {payload}")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers=self.headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    response_text = await response.text()
                    _logger.debug(f"Create task response: {response_text}")

                    if response.status != 200:
                        raise NanoBananaAPIError(
                            f"API request failed with status {response.status}: {response_text}"
                        )

                    data = json.loads(response_text)

                    if data.get("code") != 200:
                        raise NanoBananaAPIError(
                            f"API returned error code {data.get('code')}: {data.get('message')}"
                        )

                    task_id = data.get("data", {}).get("taskId")
                    if not task_id:
                        raise NanoBananaAPIError("No taskId in response")

                    _logger.info(f"Task created successfully: {task_id}")
                    return task_id

        except aiohttp.ClientError as error:
            _logger.error(f"HTTP error during createTask: {error}")
            raise NanoBananaAPIError(f"HTTP request failed: {error}")
        except json.JSONDecodeError as error:
            _logger.error(f"Failed to parse JSON response: {error}")
            raise NanoBananaAPIError(f"Invalid JSON response: {error}")

    async def query_task(self, task_id: str) -> Dict[str, Any]:
        """
        Query task status and results.

        Args:
            task_id: Task ID returned from create_task

        Returns:
            dict with task info:
                - state: "waiting", "queuing", "generating", "success", "fail"
                - resultJson: JSON string with resultUrls (if success)
                - failCode, failMsg: Error details (if fail)

        Raises:
            NanoBananaAPIError: If API request fails
        """
        url = f"{self.base_url}/api/v1/jobs/recordInfo"
        params = {"taskId": task_id}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=self.headers,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    response_text = await response.text()

                    if response.status != 200:
                        raise NanoBananaAPIError(
                            f"API request failed with status {response.status}: {response_text}"
                        )

                    data = json.loads(response_text)

                    if data.get("code") != 200:
                        raise NanoBananaAPIError(
                            f"API returned error code {data.get('code')}: {data.get('message')}"
                        )

                    task_data = data.get("data", {})
                    return task_data

        except aiohttp.ClientError as error:
            _logger.error(f"HTTP error during queryTask: {error}")
            raise NanoBananaAPIError(f"HTTP request failed: {error}")
        except json.JSONDecodeError as error:
            _logger.error(f"Failed to parse JSON response: {error}")
            raise NanoBananaAPIError(f"Invalid JSON response: {error}")

    async def wait_for_completion(
        self,
        task_id: str,
        max_attempts: int = POLLING_MAX_ATTEMPTS,
        interval: int = POLLING_INTERVAL,
        progress_callback = None,
    ) -> Dict[str, Any]:
        """
        Poll task status until completion (success or failure).

        Args:
            task_id: Task ID
            max_attempts: Maximum polling attempts
            interval: Seconds between polls
            progress_callback: Optional async callback(state, attempt, max_attempts) called on each poll

        Returns:
            Task data with resultUrls

        Raises:
            NanoBananaAPIError: If task fails or timeout
        """
        for attempt in range(max_attempts):
            task_data = await self.query_task(task_id)
            state = task_data.get("state")

            _logger.info(f"Task {task_id} status: {state} (attempt {attempt + 1}/{max_attempts})")

            # Call progress callback if provided
            if progress_callback:
                try:
                    await progress_callback(state, attempt + 1, max_attempts)
                except Exception as e:
                    _logger.warning(f"Progress callback failed: {e}")

            if state == "success":
                _logger.info(f"Task {task_id} completed successfully")
                return task_data

            if state == "fail":
                fail_code = task_data.get("failCode", "unknown")
                fail_msg = task_data.get("failMsg", "unknown error")
                _logger.error(f"Task {task_id} failed: {fail_code} - {fail_msg}")
                raise NanoBananaAPIError(f"Generation failed: {fail_msg}")

            # Still processing (waiting, queuing, generating)
            await asyncio.sleep(interval)

        # Timeout
        raise NanoBananaAPIError(f"Task {task_id} timed out after {max_attempts * interval} seconds")

    async def generate_image(
        self,
        prompt: str,
        output_format: str = "png",
        image_size: str = "1:1",
        progress_callback = None,
    ) -> List[str]:
        """
        Generate image from text prompt (text-to-image).

        Args:
            prompt: Text description
            output_format: "png" or "jpeg"
            image_size: Aspect ratio
            progress_callback: Optional async callback for progress updates

        Returns:
            List of generated image URLs

        Raises:
            NanoBananaAPIError: If generation fails
        """
        _logger.info(f"Generating image with prompt: {prompt[:50]}...")

        task_id = await self.create_task(
            prompt=prompt,
            mode="generate",
            output_format=output_format,
            image_size=image_size,
        )

        task_data = await self.wait_for_completion(task_id, progress_callback=progress_callback)

        # Parse resultJson
        result_json = task_data.get("resultJson")
        if not result_json:
            raise NanoBananaAPIError("No resultJson in completed task")

        try:
            result = json.loads(result_json)
            result_urls = result.get("resultUrls", [])
            if not result_urls:
                raise NanoBananaAPIError("No resultUrls in result")
            return result_urls
        except json.JSONDecodeError as error:
            raise NanoBananaAPIError(f"Failed to parse resultJson: {error}")

    async def edit_image(
        self,
        prompt: str,
        image_urls: List[str],
        output_format: str = "png",
        image_size: str = "1:1",
        progress_callback = None,
    ) -> List[str]:
        """
        Edit image(s) based on prompt (image-to-image).

        Args:
            prompt: Editing instructions or style application instructions
            image_urls: List of image URLs (up to 10)
            output_format: "png" or "jpeg"
            progress_callback: Optional async callback for progress updates
            image_size: Aspect ratio

        Returns:
            List of generated image URLs

        Raises:
            NanoBananaAPIError: If editing fails
        """
        _logger.info(f"Editing image(s) with prompt: {prompt[:50]}...")

        task_id = await self.create_task(
            prompt=prompt,
            mode="edit",
            image_urls=image_urls,
            output_format=output_format,
            image_size=image_size,
        )

        task_data = await self.wait_for_completion(task_id, progress_callback=progress_callback)

        # Parse resultJson
        result_json = task_data.get("resultJson")
        if not result_json:
            raise NanoBananaAPIError("No resultJson in completed task")

        try:
            result = json.loads(result_json)
            result_urls = result.get("resultUrls", [])
            if not result_urls:
                raise NanoBananaAPIError("No resultUrls in result")
            return result_urls
        except json.JSONDecodeError as error:
            raise NanoBananaAPIError(f"Failed to parse resultJson: {error}")


# Global client instance
nano_banana_client = NanoBananaClient()
