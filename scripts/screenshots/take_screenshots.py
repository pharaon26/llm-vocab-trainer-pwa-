# Скриншоты через Playwright (Chrome): запускается из корня проекта после seed_demo.py
import json, httpx
from playwright.sync_api import sync_playwright
BASE="http://localhost:8010"; PW="demo-password-1"; OUT="docs/screenshots"
cards={c["term"]:c for c in json.load(open("data/cards.json",encoding="utf-8"))}
# новый студент для экранов задания
httpx.post(BASE+"/auth/register",headers={"Origin":BASE},json={"name":"lena_demo","password":PW,"password_confirm":PW,"role":"student"})

def login(page,name,path="/"):
    page.goto(BASE+path); page.fill("#name",name); page.fill("#password",PW); page.get_by_role("button",name="Войти",exact=True).click()

def start_task(page):
    page.get_by_role("button",name="Начать повторение").click()
    page.wait_for_selector("button.option, #answer, textarea", timeout=20000)

def answer_wrong(page):
    prompt=page.locator(".prompt").inner_text()
    right=cards.get(prompt,{}).get("definition_en")
    options=page.locator("button.option")
    for i in range(options.count()):
        if options.nth(i).inner_text().strip()!=right:
            options.nth(i).click(); break
    page.get_by_role("button",name="Ответить").click()
    page.wait_for_selector(".feedback"); page.wait_for_timeout(900); page.evaluate("window.scrollTo(0,0)")

def shot(page,name): page.wait_for_timeout(500); page.screenshot(path=f"{OUT}/{name}.png")

with sync_playwright() as p:
    browser=p.chromium.launch(channel="chrome",headless=True)
    def ctx(scheme,mobile):
        if mobile: return browser.new_context(viewport={"width":390,"height":844},device_scale_factor=2,is_mobile=True,has_touch=True,color_scheme=scheme,locale="ru-RU")
        return browser.new_context(viewport={"width":1280,"height":800},device_scale_factor=1,color_scheme=scheme,locale="ru-RU")
    # телефон, светлая: задание и результат
    c=ctx("light",True); pg=c.new_page(); login(pg,"lena_demo"); pg.wait_for_selector("text=Начать повторение"); start_task(pg); pg.wait_for_timeout(700)
    pg.locator("button.option").nth(1).click(); shot(pg,"phone-light-task"); 
    pg.reload(); pg.wait_for_selector("text=Начать повторение"); start_task(pg); answer_wrong(pg); shot(pg,"phone-light-feedback"); c.close()
    # телефон, темная: задание, прогресс, статистика
    c=ctx("dark",True); pg=c.new_page(); login(pg,"lena_demo"); pg.wait_for_selector("text=Начать повторение"); start_task(pg); pg.wait_for_timeout(700); shot(pg,"phone-dark-task"); c.close()
    c=ctx("dark",True); pg=c.new_page(); login(pg,"anna_k"); pg.wait_for_selector("text=Начать повторение")
    pg.goto(BASE+"/#/progress"); pg.wait_for_selector(".row"); shot(pg,"phone-dark-progress")
    pg.goto(BASE+"/#/stats"); pg.wait_for_selector(".chart"); shot(pg,"phone-dark-stats")
    c.close()
    # телефон, светлая: мои преподаватели
    c=ctx("light",True); pg=c.new_page(); login(pg,"anna_k"); pg.wait_for_selector("text=Начать повторение"); pg.goto(BASE+"/#/teachers"); pg.wait_for_selector("text=Мои преподаватели"); pg.wait_for_selector("text=petrov_t"); shot(pg,"phone-light-teachers"); c.close()
    # ПК, светлая: результат; история темная
    c=ctx("light",False); pg=c.new_page(); login(pg,"lena_demo"); pg.wait_for_selector("text=Начать повторение"); start_task(pg); answer_wrong(pg); shot(pg,"desktop-light-feedback"); c.close()
    # ПК: кабинет преподавателя
    c=ctx("light",False); pg=c.new_page(); login(pg,"ivanova_t","/teacher.html"); pg.wait_for_selector("text=Мои студенты и группы"); pg.wait_for_selector("text=boris_dev"); shot(pg,"desktop-light-teacher-students"); c.close()
    c=ctx("dark",False); pg=c.new_page(); login(pg,"ivanova_t","/teacher.html"); pg.wait_for_selector(".tabs"); pg.get_by_role("tab",name="Аналитика").click(); pg.wait_for_selector(".chart"); shot(pg,"desktop-dark-teacher-analytics"); c.close()
    c=ctx("light",False); pg=c.new_page(); login(pg,"ivanova_t","/teacher.html"); pg.wait_for_selector(".tabs"); pg.get_by_role("tab",name="Мои наборы").click(); pg.wait_for_selector("text=Cryptography basics"); shot(pg,"desktop-light-teacher-decks"); c.close()
    browser.close()
print("done")
