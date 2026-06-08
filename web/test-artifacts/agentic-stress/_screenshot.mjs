// Headless screenshot of MACS agentic-hell session showing safety_warning UI
import { chromium } from '@playwright/test'
import fs from 'fs'

const COOKIE_FILE = '/tmp/macs-claude-cookie.txt'
const BASE = 'http://100.81.47.91:8101'
const PROJECT_ID = 22  // agentic-hell
const OUT = '/Users/shaka-mac-mini/coding-projects/macs/web/test-artifacts/agentic-stress/safety-warning-ui.png'

// Parse libcurl cookie file → cookie value
function readCookie() {
  for (const ln of fs.readFileSync(COOKIE_FILE, 'utf8').split('\n')) {
    if (!ln.trim()) continue
    let s = ln.trim()
    if (s.startsWith('#HttpOnly_')) s = s.slice('#HttpOnly_'.length)
    else if (s.startsWith('#')) continue
    const parts = s.split('\t')
    if (parts.length >= 7 && parts[5] === 'pw_session') return parts[6]
  }
  throw new Error('no pw_session cookie')
}

const cookie = readCookie()
const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  ignoreHTTPSErrors: true,
})
await context.addCookies([{
  name: 'pw_session',
  value: cookie,
  domain: '100.81.47.91',
  path: '/',
  httpOnly: true,
  secure: false,
  sameSite: 'Lax',
}])
const page = await context.newPage()
page.on('console', (m) => console.log('  [console]', m.type(), m.text().slice(0, 200)))
page.on('pageerror', (e) => console.log('  [pageerror]', e.message.slice(0, 200)))

console.log('navigating…')
await page.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 30000 })
await page.waitForTimeout(800)

// Click agentic-hell project in sidebar
console.log('clicking agentic-hell…')
const projectBtn = page.locator('text=/agentic.?hell/i').first()
await projectBtn.waitFor({ timeout: 8000 })
await projectBtn.click()
await page.waitForTimeout(1200)

// Scroll to the latest safety_warning if any
await page.evaluate(() => {
  const els = document.querySelectorAll('[data-testid^="safety-warning-"]')
  if (els.length) els[els.length - 1].scrollIntoView({ behavior: 'instant', block: 'center' })
})
await page.waitForTimeout(400)

await page.screenshot({ path: OUT, fullPage: false })
console.log('saved →', OUT)
const has = await page.evaluate(() => document.querySelectorAll('[data-testid^="safety-warning-"]').length)
console.log('safety_warning elements on page:', has)
await browser.close()
