"""
iCourse API client for Fudan University's smart teaching platform.

Provides access to course details, lecture lists, video URLs,
and video downloads through WebVPN.
"""

import hashlib
import os
import re
import time
import uuid
from datetime import date
from urllib.parse import urlparse

from . import config
from .webvpn import WebVPNSession


def playback_is_released(item: dict, now: float | None = None) -> bool:
    """Recorded media can exist before the platform's delayed release time."""
    if str(item.get("playback_status")) != "1" or item.get("show") == "no":
        return False
    now = time.time() if now is None else now
    try:
        release = max(float(item.get("sub_delayed_release") or 0), float(item.get("open_at") or 0))
        deadline = float(item.get("deadline_at") or 0)
    except (TypeError, ValueError):
        return False
    return now >= release and (deadline <= 0 or now < deadline)


class ICourseClient:
    """Client for the iCourse API, operating through WebVPN."""

    def __init__(self, vpn_session: WebVPNSession):
        self.vpn = vpn_session
        self.base_url = config.ICOURSE_BASE
        self._userinfo = None

    def get_userinfo(self) -> dict:
        """Get current user info (id, tenant_id, phone, account).

        Caches the result for the session.
        """
        if self._userinfo is not None:
            return self._userinfo

        url = f"{self.base_url}/userapi/v1/infosimple"
        resp = self.vpn.get(url)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") not in (0, 200):
            raise RuntimeError(f"Failed to get userinfo: {data.get('msg')}")

        self._userinfo = data.get("params") or data.get("data", {})
        return self._userinfo

    def check_alive(self) -> bool:
        """Quick session health check (non-cached)."""
        try:
            resp = self.vpn.get(
                f"{self.base_url}/userapi/v1/infosimple", timeout=10
            )
            return resp.status_code == 200 and resp.json().get("code") in (0, 200)
        except Exception:
            return False

    def sign_video_url(
        self, video_url: str, now: int | None = None
    ) -> str:
        """Sign a video URL with CDN authentication parameters.

        Adds clientUUID and t parameters required for video download.
        The t parameter format: {user_id}-{timestamp}-{md5_hash}
        where md5_hash = md5(pathname + user_id + tenant_id + reversed_phone + timestamp)
        """
        userinfo = self.get_userinfo()
        user_id = userinfo.get("id", "")
        tenant_id = userinfo.get("tenant_id", "")
        phone = str(userinfo.get("phone", ""))

        if now is None:
            now = int(time.time())

        reversed_phone = phone[::-1]
        pathname = urlparse(video_url).path

        hash_input = f"{pathname}{user_id}{tenant_id}{reversed_phone}{now}"
        md5_hash = hashlib.md5(hash_input.encode()).hexdigest()
        t_param = f"{user_id}-{now}-{md5_hash}"

        client_uuid = str(uuid.uuid4())
        sep = "&" if "?" in video_url else "?"
        return f"{video_url}{sep}clientUUID={client_uuid}&t={t_param}"

    def get_course_detail(self, course_id: str) -> dict:
        """Get course details including title, teacher, and lecture list.

        Returns dict with keys: title, teacher, lectures
        Each lecture has: sub_id, sub_title, lecturer_name, date, has_playback
        """
        url = f"{self.base_url}/courseapi/v3/multi-search/get-course-detail"
        resp = self.vpn.get(url, params={"course_id": course_id})
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(
                f"API error for course {course_id}: {data.get('msg')}"
            )

        course_data = data.get("data", {})
        title = course_data.get("title", "Unknown")
        teacher = course_data.get("realname", "Unknown")

        # Parse the nested sub_list: {year: {month: {day: [items]}}}
        lectures = []
        sub_list = course_data.get("sub_list", {})
        for year, months in sub_list.items():
            for month, days in months.items():
                for day, items in days.items():
                    for item in items:
                        if "id" in item:
                            # The outer sub_list groups are year/month/week,
                            # not a calendar date. The lecture title supplies
                            # the actual date (e.g. 2026-09-07第3-5节).
                            match = re.search(r"\d{4}-\d{2}-\d{2}", str(item.get("sub_title", "")))
                            lecture_date = ""
                            if match:
                                try:
                                    lecture_date = date.fromisoformat(match.group()).isoformat()
                                except ValueError:
                                    pass
                            lectures.append(
                                {
                                    "sub_id": item["id"],
                                    "sub_title": item.get("sub_title", ""),
                                    "lecturer_name": item.get(
                                        "lecturer_name", ""
                                    ),
                                    "date": lecture_date,
                                    "has_playback": playback_is_released(item),
                                }
                            )

        return {"title": title, "teacher": teacher, "lectures": lectures}

    def get_course_list(
        self,
        term: str = "24",
        page: int = 1,
        per_page: int = 20,
        title: str = "",
    ) -> dict:
        """Get a paginated list of courses for a given term.

        Returns dict with keys: total, courses (list of course dicts)
        """
        url = f"{self.base_url}/portal/courseapi/v3/multi-search/get-course-list"
        params = {
            "tenant": config.TENANT_CODE,
            "title": title,
            "term": term,
            "kkxy_code": "",
            "course_type": "",
            "course_student_type": "",
            "page": page,
            "per_page": per_page,
        }
        resp = self.vpn.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(f"API error: {data.get('msg')}")

        result = data.get("data", {})
        return {
            "total": int(result.get("total", 0)),
            "courses": result.get("list", []),
        }

    def get_lecture_detail(self, course_id: str, sub_id: str) -> dict:
        """Get details for a specific lecture, including video URL info.

        The video URL is typically embedded in the course detail's sub_list
        items. This method retrieves the full course detail and finds the
        matching lecture by sub_id.
        """
        detail = self.get_course_detail(course_id)
        for lecture in detail["lectures"]:
            if str(lecture["sub_id"]) == str(sub_id):
                return lecture
        raise ValueError(
            f"Lecture {sub_id} not found in course {course_id}"
        )

    def get_transcript(self, sub_id: str) -> str | None:
        """Get the transcript text for a lecture.

        Returns the full transcript text, empty string if no transcript,
        or None on error.
        """
        url = f"{self.base_url}/courseapi/v3/web-socket/search-trans-result"
        resp = self.vpn.get(
            url, params={"sub_id": sub_id, "format": "json"}
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            return None

        result_list = data.get("list", [])
        if not result_list:
            return ""

        all_content = result_list[0].get("all_content", [])
        if not all_content:
            return ""

        all_content.sort(key=lambda x: x.get("BeginSec", 0))
        return " ".join(
            seg.get("Text", "") for seg in all_content if seg.get("Text")
        )

    def get_sub_detail(self, course_id: str, sub_id: str) -> dict:
        """Get detailed info for a specific lecture (unsigned URL).

        Returns the full sub-detail data from the API.
        Note: The video URL returned here is NOT signed for CDN auth.
        Use get_sub_info() instead for a signed/downloadable URL.
        """
        url = f"{self.base_url}/courseapi/v3/multi-search/get-sub-detail"
        resp = self.vpn.get(url, params={
            "course_id": course_id, "sub_id": sub_id
        })
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(
                f"API error for sub {sub_id}: {data.get('msg')}"
            )

        return data.get("data", {})

    def get_sub_info(self, course_id: str, sub_id: str) -> dict:
        """Get lecture info including video URLs and timestamp.

        Returns the full sub-info data from the API.
        The playurl dict maps stream indices to video URLs.
        The 'now' field provides the server timestamp for CDN signing.
        """
        url = (
            f"{self.base_url}"
            f"/courseapi/v3/portal-home-setting/get-sub-info"
        )
        resp = self.vpn.get(url, params={
            "course_id": course_id, "sub_id": sub_id
        })
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(
                f"API error for sub-info {sub_id}: {data.get('msg')}"
            )

        return data.get("data", {})

    def get_video_url(self, course_id: str, sub_id: str) -> str | None:
        """Get a signed MP4 video URL for a specific lecture.

        Uses the get-sub-info API to get the base video URL, then
        signs it with CDN authentication parameters (clientUUID, t).

        Returns the signed video URL string if found, None otherwise.
        """
        try:
            info = self.get_sub_info(course_id, sub_id)
        except Exception as e:
            print(f"    Failed to get sub info for {sub_id}: {type(e).__name__}")
            return None

        # Get server timestamp for signing
        now = info.get("now")
        if isinstance(now, str):
            now = int(now)

        # Extract base video URL from playurl dict or video_list
        base_url = None

        # Try video_list first (has preview_url without /0/ prefix)
        video_list = info.get("video_list", {})
        if isinstance(video_list, dict):
            for _, v in video_list.items():
                if isinstance(v, dict):
                    preview = v.get("preview_url")
                    if preview and preview.endswith(".mp4"):
                        base_url = preview
                        break

        # Fallback: try playurl dict (has /0/ prefix, may need stripping)
        if not base_url:
            playurl = info.get("playurl", {})
            if isinstance(playurl, dict):
                for k, v in playurl.items():
                    if k == "now":
                        continue
                    if isinstance(v, str) and v.endswith(".mp4"):
                        base_url = v
                        break

        # Last resort: try unsigned get-sub-detail
        if not base_url:
            try:
                detail = self.get_sub_detail(course_id, sub_id)
                content = detail.get("content", {})
                playback = content.get("playback", {})
                if playback and playback.get("url"):
                    base_url = playback["url"]
            except Exception:
                pass

        if not base_url:
            print(f"    No video URL found for {sub_id} (tried video_list, playurl, sub_detail)")
            return None

        return self.sign_video_url(base_url, now=now)

    def get_stream_params(self, video_url: str) -> tuple[str, str]:
        """Get WebVPN URL and HTTP headers for direct streaming (e.g., ffmpeg).

        Returns:
            (vpn_url, http_headers) where http_headers is ffmpeg-compatible.
        """
        from .webvpn import get_vpn_url
        vpn_url = get_vpn_url(video_url)
        cookies = "; ".join(
            f"{c.name}={c.value}" for c in self.vpn.session.cookies
        )
        headers = f"Cookie: {cookies}\r\nUser-Agent: {config.USER_AGENT}\r\n"
        return vpn_url, headers

    def download_video(
        self,
        video_url: str,
        output_path: str,
        chunk_size: int = 8192,
    ) -> str:
        """Download a video file from the given URL.

        If video_url is a WebVPN URL, uses get_raw; otherwise uses get.
        Returns the output file path.
        """
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        tmp_path = output_path + ".tmp"
        t0 = time.time()

        if video_url.startswith(config.WEBVPN_BASE):
            resp = self.vpn.get_raw(video_url, stream=True, timeout=300)
        else:
            resp = self.vpn.get(video_url, stream=True, timeout=300)

        resp.raise_for_status()

        total = int(resp.headers.get("content-length", 0))
        downloaded = 0

        with open(tmp_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded * 100 // total
                    print(
                        f"\r    Downloading: {pct}% "
                        f"({downloaded // 1024 // 1024}MB/"
                        f"{total // 1024 // 1024}MB)",
                        end="",
                        flush=True,
                    )

        print()  # newline after progress

        if total and downloaded < total:
            os.remove(tmp_path)
            raise RuntimeError(
                f"Incomplete download: got {downloaded} of {total} bytes"
            )

        os.replace(tmp_path, output_path)
        elapsed = time.time() - t0
        size_mb = downloaded / (1024 * 1024)
        print(f"    Downloaded: {size_mb:.1f}MB in {elapsed:.0f}s")
        return output_path
