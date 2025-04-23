from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

import dotenv
import os
import re
import json
from datetime import datetime
import requests
from tqdm import tqdm
import hashlib

BASE_URL = "https://echo360.net.au"
LOGIN_MAIN_URL = "https://login.echo360.net.au/login"
LOGIN_ALTERNATE_URL = f"{BASE_URL}/directLogin"
COURSES_URL = f"{BASE_URL}/courses"
CDN_BASE_URL = "https://content.echo360.net.au"
DOWNLOADS_FOLDER_NAME = "downloads"
TARGET_COURSE_CODES = ["COMP6843"]
SOURCE_NUM = 1
QUALITY = "HD"

START_INDEX = 0

assert SOURCE_NUM in {1, 2}
assert QUALITY in {"HD", "SD"}

dotenv.load_dotenv()

class Video:
    def __init__(self, source_num: int, quality: str, size: str, url: str = None):
        self._lecture = None
        self.source_num = source_num
        self.quality = quality
        self.size = size
        self.url = url
        self.file_path = None
        self._sha256 = None

    @property
    def lecture(self):
        return self._lecture

    @lecture.setter
    def lecture(self, lecture: "Lecture"):
        if self._lecture is not None:
            raise ValueError(f"Video already belongs to lecture: {self._lecture}")
        self._lecture = lecture

    @property
    def sha256(self) -> str:
        return self._sha256

    def generate_video_filename(self, extension: str = "mp4") -> str:
        course_codes = '-'.join(self.lecture.course.course_codes)
        date_formatted = f"{self.lecture.date.year}-{self.lecture.date.month}-{self.lecture.date.day}"
        time_formatted = f"{self.lecture.start_time.hour}-{self.lecture.start_time.minute}"
        date_and_time = f"{date_formatted}-{time_formatted}"
        return f"{course_codes}_Lecture-{self.lecture.lecture_num}_{date_and_time}_Source-{self.source_num}_Quality-{self.quality}.{extension}"

    def calculate_sha256_hash(self, file_path: str) -> str:
        self.file_path = file_path
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        self._sha256 = sha256_hash.hexdigest()
        return self._sha256

    def to_dict(self) -> dict:
        return {
            "source_num": self.source_num,
            "quality": self.quality,
            "size": self.size,
            "downloaded_url": self.url,
            "sha256": self._sha256,
            "file_path": str(self.file_path) if self.file_path else None
        }

class Lecture:
    def __init__(self, course: "Course", title: str, date: datetime.date,
                 start_time: datetime.time, end_time: datetime.time,
                 lecture_num: int, videos: list[Video]):
        self.course = course
        self.title = title
        self.date = date
        self.start_time = start_time
        self.end_time = end_time
        self.lecture_num = lecture_num
        self.videos = videos
        for video in self.videos:
            video.lecture = self

    def add_video(self, video: Video):
        self.videos.append(video)

    def to_dict(self) -> dict:
        return {
            "course": self.course,
            "lecture_num": self.lecture_num,
            "title": self.title,
            "date": self.date,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "videos": self.videos,
        }

class Course:
    def __init__(self, course_codes: list[str], course_name: str, year: int,
                 term: int, lecture_count: int, url: str):
        self.course_codes = course_codes
        self.course_name = course_name
        self.year = year
        self.term = term
        self.lecture_count = lecture_count
        self.url = url
        self.lectures: list[Lecture] = []

    def add_lecture(self, lecture: Lecture):
        if lecture.course is not self:
            raise ValueError("Lecture belongs to another course")
        if len(self.lectures) >= int(self.lecture_count):
            raise ValueError(f"Cannot add more lectures than {self.lecture_count = }")
        self.lectures.append(lecture)

    def to_dict(self) -> dict:
        return {
            "course_codes": self.course_codes,
            "course_name": self.course_name,
            "year": self.year,
            "term": self.term,
            "lecture_count": self.lecture_count,
            "url": self.url,
            "lectures": [v.to_dict() for v in self.lectures]
        }

    def scrape_course(self, driver: webdriver.Chrome, start_index: int = START_INDEX):
        driver.get(self.url)
        lecture_rows = WebDriverWait(driver, 2).until(
            EC.presence_of_all_elements_located((By.CLASS_NAME, "class-row"))
        )

        for row in lecture_rows[start_index:]:
            title = row.find_element(By.CSS_SELECTOR, 'div[role="title"].title').text.strip()
            date_str = row.find_element(By.CLASS_NAME, "date").text.strip()
            time_str = row.find_element(By.CLASS_NAME, "time").text.strip()

            date_obj = datetime.strptime(date_str, "%B %d, %Y").date()
            start_time_str, end_time_str = time_str.split("-")
            start_time = datetime.strptime(start_time_str, "%I:%M%p").time()
            end_time = datetime.strptime(end_time_str, "%I:%M%p").time()

            try:
                # Open video menu
                self._await_clickable(By.CSS_SELECTOR, 'div.courseMediaIndicator[data-test-id="open-class-video-menu"]', row, 0).click()

                # Click download original
                self._await_clickable(By.CSS_SELECTOR, 'a[data-test-id="download-class-media"]', row).click()
            except AttributeError:
                continue

            # Wait for "Download" dialog box to load
            download_dialog = self._await_clickable(By.ID, "download-tabs", driver)

            videos = []
            sources = download_dialog.find_elements(By.CSS_SELECTOR, 'div[data-test-component="DownloadRow"]')
            for source in sources:
                source_element = source.find_element(By.CSS_SELECTOR, 'div[data-test-component="PosterOverlay"]')
                source_num = int(source_element.text.strip()[-1])

                quality_options = source.find_elements(By.CSS_SELECTOR, 'div[data-test-component="DownloadFile"]')
                for option in quality_options:
                    button_aria_label = option.find_element(By.TAG_NAME, "button").get_attribute("aria-label")

                    quality = "HD" if "Full Quality" in button_aria_label else "SD"

                    size_match = re.search(r'(\d+\.?\d*)\s?(MB|GB)', button_aria_label)
                    size = f"{size_match.group(1)} {size_match.group(2)}"

                    download_button = self._await_clickable(By.CSS_SELECTOR, f'button[data-test-id="video{str(source_num)}-{quality.lower()}-download"]', download_dialog)
                    downloaded_video_url = self.download_video_and_get_url(driver, download_button) if source_num == SOURCE_NUM and quality == QUALITY else None

                    videos.append(Video(
                        source_num=source_num,
                        quality=quality,
                        size=size,
                        url=downloaded_video_url
                    ))

            # Close "Download" dialog box
            self._await_clickable(By.CSS_SELECTOR, 'div[data-test-component="DownloadMedia"] button[aria-label="Close"]', driver).click()

            lecture_num = len(self.lectures) + 1
            self.add_lecture(Lecture(
                course=self,
                title=title,
                date=date_obj,
                start_time=start_time,
                end_time=end_time,
                lecture_num=lecture_num,
                videos=videos,
            ))

        driver.get(COURSES_URL)

    def download_video_and_get_url(self, driver: webdriver.Chrome, download_button) -> str:
        driver.get_log("performance")

        # Download video
        download_button.click()

        logs = driver.get_log("performance")
        for entry in logs:
            try:
                log = json.loads(entry["message"])["message"]
                if log["method"] == "Network.requestWillBeSent":
                    url = log["params"]["request"]["url"]
                    if CDN_BASE_URL in url:
                        return url
            except Exception:
                continue

    def _await_clickable(self, by: str, value: str, driver, timeout: int = 2):
        try:
            return WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((by, value))
            )
        except TimeoutException:
            return None

def login(driver: webdriver.Chrome, email=os.getenv("EMAIL"), region="echo360.org.au", password=os.getenv("PASSWORD"), login_url=LOGIN_ALTERNATE_URL):
    driver.get(login_url)

    email_field = driver.find_element(By.NAME, "email")
    email_field.send_keys(email)

    # There's only 1 "select" tag in the alternate login page
    region_dropdown = driver.find_element(By.TAG_NAME, "select")
    region_select = Select(region_dropdown)
    region_select.select_by_value(region)

    password_field = driver.find_element(By.NAME, "password")
    password_field.send_keys(password)

    submit_button = driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]')
    submit_button.click()

def expand_course_codes(course_codes_str: str) -> list[str]:
    course_codes = set()
    curr_prefix = None

    for part in course_codes_str.split('/'):
        if match := re.match(r'^([A-Za-z]+)(\d+)$', part):
            curr_prefix = match.group(1)
            course_codes.add(part)
        elif curr_prefix:
            course_codes.add(f"{curr_prefix}{part}")

    return list(course_codes)

def get_courses(driver: webdriver.Chrome) -> list[Course]:
    driver.get(COURSES_URL)
    course_cells = WebDriverWait(driver, 10).until(
        EC.presence_of_all_elements_located(
            (By.CSS_SELECTOR, 'div[role="row"] > span[role="gridcell"]')
        )
    )

    courses = []
    for cell in course_cells:
        url = cell.find_element(By.TAG_NAME, 'a').get_attribute("href")

        lecture_count = cell.find_element(
            By.CSS_SELECTOR, "span.SectionCard__LessonCount-sc-757pmy-1"
        ).text

        term = cell.find_element(
            By.CSS_SELECTOR, "div.SectionCard__TermAndDate-sc-757pmy-2"
        ).get_attribute("title")[-1]

        year = cell.find_element(
            By.CSS_SELECTOR, "span.commonComponents__CardName-sc-1pafgjx-18"
        ).get_attribute("title")[:4]

        course_info = cell.find_element(
            By.CSS_SELECTOR, "span.SectionCard__CourseInfo-sc-757pmy-3"
        ).get_attribute("title")

        course_codes_str, course_name = course_info.strip().split(' - ', 1)

        courses.append(Course(
            course_codes=expand_course_codes(course_codes_str),
            course_name=course_name,
            year=year,
            term=term,
            lecture_count=lecture_count,
            url=url
        ))

    return courses

def download_video(video: Video, filename: str):
    response = requests.get(video.url, stream=True)
    file_size = int(response.headers.get("content-length", 0))
    progress = tqdm(total=file_size, unit='B', unit_scale=True, desc=filename)

    download_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), DOWNLOADS_FOLDER_NAME)
    os.makedirs(download_dir, exist_ok=True)
    file_path = os.path.join(download_dir, filename)

    chunk_size = 1024 * 1024 # 1MB
    with open(file_path, "wb") as file:
        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk:
                file.write(chunk)
                progress.update(len(chunk))

    progress.close()
    video.calculate_sha256_hash(file_path)

def main():
    try:
        chrome_options = webdriver.ChromeOptions()
        chrome_options.enable_downloads = True
        chrome_options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
        chrome_options.add_experimental_option("prefs", {
            "download.default_directory": os.path.abspath("chrome_downloads"),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True
        })

        driver = webdriver.Chrome(chrome_options)

        login(driver)
        courses = get_courses(driver)

        target_courses: list[Course] = []
        for course in courses:
            if any(code in course.course_codes for code in TARGET_COURSE_CODES):
                target_courses.append(course)

        for target_course in target_courses:
            target_course.scrape_course(driver)
    finally:
        driver.quit()

    for target_course in target_courses:
        for lecture in target_course.lectures:
            for video in lecture.videos:
                if video.url:
                    download_video(video, video.generate_video_filename())

if __name__ == "__main__":
    main()