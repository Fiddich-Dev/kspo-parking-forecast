// 키보드만으로 네 화면을 오가고 공연 카드의 버튼까지 닿는지 본다.
// 사용: npm i playwright@1.49.1 (아무 폴더) 뒤 NODE_PATH=<그 폴더>/node_modules node scripts/keyboard_check.cjs [주소]. 설치된 Google Chrome을 쓴다
const { chromium } = require("playwright");
(async () => {
const url = process.argv[2] || "http://localhost:8767/";
const b = await chromium.launch({ channel: "chrome" });
const p = await b.newPage({ viewport: { width: 390, height: 844 } });
await p.goto(url); await p.waitForTimeout(1000);
const seen = [];
for (let i = 0; i < 12; i++) { await p.keyboard.press("Tab"); seen.push(await p.evaluate(() => document.activeElement.textContent.trim().slice(0, 12))); }
console.log("Tab 순서:", seen.join(" | "));
for (const tab of ["예보 달력", "공연", "성적표", "지금"]) {
  await p.focus(`nav a:text-is("${tab}")`); await p.keyboard.press("Enter"); await p.waitForTimeout(300);
  console.log(tab, "->", await p.evaluate(() => location.hash + " " + document.querySelector("h2").textContent));
}
await p.goto(url + "#events"); await p.waitForTimeout(500);
await p.focus("ul.events a"); await p.keyboard.press("Enter"); await p.waitForTimeout(300);
await p.focus("#copy"); await p.keyboard.press("Enter"); await p.waitForTimeout(300);
console.log("공연 카드:", await p.evaluate(() => location.hash), "| 복사 결과:", await p.textContent("#copied"));
for (const h of ["#now", "#calendar", "#events", "#score", "#event/5158/2026-11-21"]) {
  await p.goto(url + h); await p.waitForTimeout(500);
  console.log("가로 넘침", h, await p.evaluate(() => document.documentElement.scrollWidth > window.innerWidth));
}
await b.close();
})();
