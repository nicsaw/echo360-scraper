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

BASE_URL = "https://echo360.net.au"
LOGIN_MAIN_URL = "https://login.echo360.net.au/login"
LOGIN_ALTERNATE_URL = f"{BASE_URL}/directLogin"
COURSES_URL = f"{BASE_URL}/courses"
CDN_BASE_URL = "https://content.echo360.net.au"

dotenv.load_dotenv()

class Lecture:
    def __init__(self, course: "Course", title: str, date: datetime.date,
                 start_time: datetime.time, end_time: datetime.time,
                 videos: list[dict]):
        self.course = course
        self.title = title
        self.date = date
        self.start_time = start_time
        self.end_time = end_time
        self.videos = videos

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "date": self.date,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "videos": self.videos,
        }

class Course:
    def __init__(self, course_codes: list[str], course_name: str, year: str, term: str, lecture_count: str, url: str):
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

    def scrape_course(self, driver: webdriver.Chrome):
        driver.get(self.url)
        sessions = WebDriverWait(driver, 2).until(
            EC.presence_of_all_elements_located((By.CLASS_NAME, "class-row"))
        )

        for session in sessions:
            title = session.find_element(By.CSS_SELECTOR, 'div[role="title"].title').text.strip()
            date_str = session.find_element(By.CLASS_NAME, "date").text.strip()
            time_str = session.find_element(By.CLASS_NAME, "time").text.strip()

            date_obj = datetime.strptime(date_str, "%B %d, %Y").date()
            start_time_str, end_time_str = time_str.split("-")
            start_time = datetime.strptime(start_time_str, "%I:%M%p").time()
            end_time = datetime.strptime(end_time_str, "%I:%M%p").time()

            try:
                self._await_clickable(By.CSS_SELECTOR, 'div.courseMediaIndicator[data-test-id="open-class-video-menu"]', session).click()
            except AttributeError:
                continue

            # Click download original
            self._await_clickable(By.CSS_SELECTOR, 'a[data-test-id="download-class-media"]', session).click()

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
                    if source_num == 1 and quality == "HD":
                        downloaded_video_url = self.download_video_and_get_url(driver, download_button)
                    else:
                        downloaded_video_url = None

                    videos.append({
                        "video_source_num": source_num,
                        "quality": quality,
                        "size": size,
                        "downloaded_video_url": downloaded_video_url,
                    })

            # Close "Download" dialog box
            self._await_clickable(By.CSS_SELECTOR, 'div[data-test-component="DownloadMedia"] button[aria-label="Close"]', driver).click()

            self.add_lecture(Lecture(
                course=self,
                title=title,
                date=date_obj,
                start_time=start_time,
                end_time=end_time,
                videos=videos,
            ))

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

def main():
    chrome_options = webdriver.ChromeOptions()
    chrome_options.enable_downloads = True
    chrome_options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    driver = webdriver.Chrome(chrome_options)

    login(driver)
    courses = get_courses(driver)
    courses[0].scrape_course(driver)

    driver.quit()

if __name__ == "__main__":
    main()