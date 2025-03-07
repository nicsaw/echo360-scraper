from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
import dotenv
import os

BASE_URL = "https://echo360.net.au"
ALTERNATE_LOGIN_URL = f"{BASE_URL}/directLogin"

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

def main():
    driver = webdriver.Chrome()
    login(driver)
    driver.quit()

if __name__ == "__main__":
    main()