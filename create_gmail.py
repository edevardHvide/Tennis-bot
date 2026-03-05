"""
Open Gmail signup in a visible browser, fill what we can, leave open for manual completion.
"""
import asyncio
from playwright.async_api import async_playwright

FIRST_NAME = "Tennis"
LAST_NAME = "Bot"
USERNAME = "tennisbotmatchi"
PASSWORD = "TennisBotM@tchi2025!"


async def create_gmail():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=500)
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await context.new_page()

        print("Opening Gmail signup...")
        await page.goto("https://accounts.google.com/signup/v2/createaccount?flowName=GlifWebSignIn&flowEntry=SignUp")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)

        # Dump all input fields to understand page structure
        inputs = await page.eval_on_selector_all("input", "els => els.map(e => ({name: e.name, id: e.id, type: e.type, placeholder: e.placeholder}))")
        print("Inputs on page:", inputs)

        buttons = await page.eval_on_selector_all("button", "els => els.map(e => e.innerText.trim())")
        print("Buttons on page:", buttons)

        # Try to fill first name
        for selector in ['input[name="firstName"]', 'input#firstName', 'input[autocomplete="given-name"]']:
            try:
                el = page.locator(selector)
                if await el.count() > 0:
                    await el.fill(FIRST_NAME)
                    print(f"Filled first name via {selector}")
                    break
            except Exception:
                pass

        # Try to fill last name
        for selector in ['input[name="lastName"]', 'input#lastName', 'input[autocomplete="family-name"]']:
            try:
                el = page.locator(selector)
                if await el.count() > 0:
                    await el.fill(LAST_NAME)
                    print(f"Filled last name via {selector}")
                    break
            except Exception:
                pass

        # Click Next
        for selector in ['button:has-text("Next")', 'button[type="submit"]']:
            try:
                el = page.locator(selector).first
                if await el.count() > 0:
                    await el.click()
                    print(f"Clicked next via {selector}")
                    await asyncio.sleep(2)
                    break
            except Exception:
                pass

        print("\n" + "="*60)
        print("Browser is open — please complete signup manually.")
        print(f"Suggested email: {USERNAME}@gmail.com")
        print(f"Suggested password: {PASSWORD}")
        print("="*60)
        print("Keeping browser open for 10 minutes...")
        await asyncio.sleep(600)

        await browser.close()


asyncio.run(create_gmail())
