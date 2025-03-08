from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import dotenv
import os
import re
import json

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

def get_courses(driver: webdriver.Chrome, courses_url=COURSES_URL):
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

    for course in courses:
        print(json.dumps(course, indent=2))

def main():
    driver = webdriver.Chrome()

    login(driver)
    get_courses(driver)

    driver.quit()

if __name__ == "__main__":
    main()