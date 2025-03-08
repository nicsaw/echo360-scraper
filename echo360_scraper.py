from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import dotenv
import os
import re
import json
from typing import Any
from datetime import datetime

BASE_URL = "https://echo360.net.au"
MAIN_LOGIN_URL = "https://login.echo360.net.au/login"
ALTERNATE_LOGIN_URL = f"{BASE_URL}/directLogin"
COURSES_URL = f"{BASE_URL}/courses"

dotenv.load_dotenv()

def login(driver: webdriver.Chrome, email=os.getenv("EMAIL"), region="echo360.org.au", password=os.getenv("PASSWORD"), login_url=ALTERNATE_LOGIN_URL):
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

def get_courses(driver: webdriver.Chrome, courses_url=COURSES_URL) -> list[dict[str, Any]]:
    driver.get(courses_url)
    course_cells = WebDriverWait(driver, 10).until(
        EC.presence_of_all_elements_located(
            (By.CSS_SELECTOR, 'div[role="row"] > span[role="gridcell"]')
        )
    )

    courses = []
    for cell in course_cells:
        link = cell.find_element(By.TAG_NAME, 'a').get_attribute("href")

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

        courses.append({
            "course_codes": expand_course_codes(course_codes_str),
            "course_name": course_name,
            "year": year,
            "term": term,
            "lecture_count": lecture_count,
            "link": link,
        })

    return courses

def scrape_course(course_url: str, driver: webdriver.Chrome):
    driver.get(course_url)
    sessions = WebDriverWait(driver, 10).until(
        EC.presence_of_all_elements_located((By.CLASS_NAME, "class-row"))
    )

    course_data = []
    for session in sessions:
        title = session.find_element(By.CSS_SELECTOR, 'div[role="title"].title').text.strip()
        date_str = session.find_element(By.CLASS_NAME, "date").text.strip()
        time_str = session.find_element(By.CLASS_NAME, "time").text.strip()

        date_obj = datetime.strptime(date_str, "%B %d, %Y").date()
        start_time_str, end_time_str = time_str.split("-")
        start_time = datetime.strptime(start_time_str, "%I:%M%p").time()
        end_time = datetime.strptime(end_time_str, "%I:%M%p").time()

        # Open video menu
        WebDriverWait(session, 10).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, 'div.courseMediaIndicator[data-test-id="open-class-video-menu"]')
            )
        ).click()

        # Click "Download Original"
        WebDriverWait(session, 10).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, 'a[data-test-id="download-class-media"]')
            )
        ).click()

        # Click on Video 1 HD Download button
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, 'button[data-test-id="video1-hd-download"]')
            )
        ).click()

        # Close "Download" dialog box
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, 'div[data-test-component="DownloadMedia"] button[aria-label="Close"]')
            )
        ).click()

        course_data.append({
            "title": title,
            "date": date_obj,
            "start_time": start_time,
            "end_time": end_time,
        })

    return course_data

def main():
    options = webdriver.ChromeOptions()
    options.enable_downloads = True
    driver = webdriver.Chrome()

    login(driver)
    courses = get_courses(driver)
    for course in courses:
        print(json.dumps(course, indent=2))

    COMP4337_URL = courses[1].get("link")
    COMP4337_lectures = scrape_course(COMP4337_URL, driver)
    for lecture in COMP4337_lectures:
        print(f"{lecture = }")

    driver.quit()

if __name__ == "__main__":
    main()