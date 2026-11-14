// 올팍 주차예보 화면. 빌드 도구 없이 data/*.json을 읽어 그린다.
"use strict";
const $main = document.getElementById("main");
const D = {};
const TRANSIT = "공원 내 대형행사가 개최될 경우 주차장이 혼잡하오니 반드시 버스, 지하철 등 대중교통을 이용해 주시기 바랍니다.";
const GRADES = [[0.9, "만차", "만", "g-full"], [0.7, "혼잡", "혼", "g-busy"], [0.5, "보통", "보", "g-mid"], [0, "여유", "여", "g-free"]];

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (n) => (n == null ? "값 없음" : Number(n).toLocaleString("ko-KR"));
const tm = (iso) => (iso ? new Date(iso).toLocaleString("ko-KR", { timeZone: "Asia/Seoul", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }) : "없음");
const grade = (v) => GRADES.find(([r]) => v >= r * D.fc.cap);
const toMin = (t) => { const [h, m] = t.split(":").map(Number); return h * 60 + m; };
const hm = (min) => (min == null ? "없음" : `${String(Math.floor(min / 60) % 24).padStart(2, "0")}:${String(min % 60).padStart(2, "0")}`);
const dayLabel = (iso) => { const d = new Date(iso + "T00:00:00+09:00"); return `${d.getMonth() + 1}/${d.getDate()}(${"일월화수목금토"[d.getDay()]})`; };
const todayIso = () => new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);

async function load() {
  const get = (n) => fetch(`data/${n}.json`, { cache: "no-cache" }).then((r) => (r.ok ? r.json() : null)).catch(() => null);
  [D.fc, D.now, D.ev, D.sc, D.calls] = await Promise.all(["forecast", "now", "events", "scorecard", "calls"].map(get));
  if (!D.fc) { $main.innerHTML = "<p>자료를 불러오지 못했습니다. 잠시 뒤 다시 열어 주세요.</p>"; return; }
  document.getElementById("updated").textContent = `예보 마지막 갱신 ${tm(D.fc.generated_at)} · 일정 읽은 시각 ${tm(D.ev?.read_at)}`;
  route();
}

// ---------- 그래프 ----------
function chart(day, opts = {}) {
  const W = 360, H = 210, L = 34, R = 8, T = 10, B = 24, cap = D.fc.cap, h0 = 6, h1 = 24;
  const x = (k) => L + ((k * 10 / 60 - h0) / (h1 - h0)) * (W - L - R);
  const y = (v) => T + (1 - v / cap) * (H - T - B);
  const ks = []; for (let k = h0 * 6; k < h1 * 6; k++) ks.push(k);
  const path = (arr) => ks.map((k, i) => `${i ? "L" : "M"}${x(k).toFixed(1)},${y(arr[k]).toFixed(1)}`).join("");
  const band = path(day.hi) + ks.slice().reverse().map((k) => `L${x(k).toFixed(1)},${y(day.lo[k]).toFixed(1)}`).join("") + "Z";
  let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opts.aria || "")}">`;
  for (const [r, lab] of [[0.9, "90%"], [0.7, "70%"]]) s += `<line x1="${L}" x2="${W - R}" y1="${y(r * cap)}" y2="${y(r * cap)}" stroke="#8b95a1" stroke-dasharray="4 3"/><text x="2" y="${y(r * cap) + 4}">${lab}</text>`;
  s += `<line x1="${L}" x2="${W - R}" y1="${y(0)}" y2="${y(0)}" stroke="#d1d6db"/><text x="2" y="${y(0) + 4}">0</text>`;
  for (let h = h0; h <= h1; h += 3) s += `<text x="${x(h * 6) - (h === h1 ? 22 : 8)}" y="${H - 6}">${h}시</text>`;
  s += `<path d="${band}" fill="#1b64da" fill-opacity="0.15"/><path d="${path(day.mid)}" fill="none" stroke="#1b64da" stroke-width="2.5"/>`;
  for (const [t, v] of opts.points || []) { const k = toMin(t) / 10; if (k >= h0 * 6) s += `<circle cx="${x(k)}" cy="${y(Math.max(0, Math.min(cap, v)))}" r="2.6" fill="#191f28"/>`; }
  if (opts.nowLine) { const k = opts.nowLine / 10; if (k >= h0 * 6) s += `<line x1="${x(k)}" x2="${x(k)}" y1="${T}" y2="${H - B}" stroke="#191f28" stroke-width="1"/>`; }
  return s + "</svg>";
}
function chartTable(day) {
  let rows = ""; for (let h = 6; h < 24; h++) { const k = h * 6; const g = grade(day.mid[k]); rows += `<tr><th scope="row">${h}:00</th><td>${fmt(day.lo[k])}</td><td>${fmt(day.mid[k])}</td><td>${fmt(day.hi[k])}</td><td>${g[1]}</td></tr>`; }
  return `<details><summary>표로 보기</summary><div class="scroll"><table><thead><tr><th scope="col">시각</th><th scope="col">낮게</th><th scope="col">가운데</th><th scope="col">높게</th><th scope="col">등급</th></tr></thead><tbody>${rows}</tbody></table></div></details>`;
}
const legend = (pts) => `<ul class="legend"><li><span class="sw" style="background:#1b64da"></span>예보 가운데 값</li><li><span class="sw" style="background:#1b64da;opacity:.3;height:10px"></span>낮게~높게 범위</li><li><span class="sw" style="background:#8b95a1"></span>점선: 70%·90% 문턱</li>${pts ? '<li><span class="sw" style="background:#191f28;width:6px;height:6px;border-radius:3px"></span>실측(보정값)</li>' : ""}</ul>`;
const labelTag = (l) => `<span class="label">${esc(l)}</span>`;

// ---------- 화면 1: 지금 ----------
function viewNow() {
  const day = D.fc.days.find((d) => d.date === todayIso()) || D.fc.days[0];
  const n = D.now || {}, bc = n.baseline || {};
  const nowMin = (() => { const d = new Date(Date.now() + 9 * 3600e3); return d.getUTCHours() * 60 + d.getUTCMinutes(); })();
  const pts = bc.confirmed ? (n.today || []).map(([t, v]) => [t, v - bc.offset]) : [];
  const stale = n.last && Date.now() - new Date(n.last.at) > 90 * 60e3;
  let h = `<h2>지금 <span class="muted">${dayLabel(day.date)} ${esc(day.type_ko)}</span></h2>`;
  h += `<section class="card" aria-labelledby="rt"><h3 id="rt" style="margin-top:0">실시간 주차대수 (동2문·남2문·북2문 합계)</h3>`;
  h += `<p class="big">${n.last ? fmt(n.last.value) + "대" : "값 없음"}</p><p class="muted">주최 제공 값 · ${tm(n.last?.at)} 수집${stale ? " · <strong>마지막 수집이 90분 넘게 지났습니다</strong>" : ""}</p>`;
  if (bc.confirmed) h += `<p>보정값(새벽 최저값 기준) <strong>${fmt(n.last.value - bc.offset)}대</strong> · 2,200대 중 ${Math.round((100 * (n.last.value - bc.offset)) / D.fc.cap)}%</p>`;
  else h += `<p class="muted">이 값에는 출차 기록이 없는 차가 쌓여 있는 것으로 보입니다(새벽 최저 ${fmt(Object.values(bc.nights || {}).slice(-1)[0])}대, 2024년 7월 같은 시각 평균 ${fmt(bc.night_ref_2024_07)}대). 여러 밤의 기록으로 확인하기 전에는 점유율과 만차 판단에 쓰지 않습니다. <a href="#score">확인 현황</a></p>`;
  h += `</section>`;
  if (day.transit_advice) h += `<p class="advice" role="note"><strong>오늘은 대중교통을 권합니다.</strong> 예보 범위의 높은 값이 90%를 넘습니다. 주최 안내: “${TRANSIT}”</p>`;
  h += `<section aria-labelledby="fc"><h3 id="fc">오늘 예보 ${labelTag(day.label)}</h3>`;
  h += `<dl class="kv"><dt>차기 시작(70%)</dt><dd>${day.reach70 || "닿지 않음"}</dd><dt>가득 참(90%)</dt><dd>${day.reach90 || "닿지 않음"}</dd><dt>가장 많을 때</dt><dd>${fmt(day.max_mid)}대</dd></dl>`;
  h += chart(day, { points: pts, nowLine: nowMin, aria: `오늘 시간대별 예상 주차대수. 70% 도달 ${day.reach70 || "없음"}, 90% 도달 ${day.reach90 || "없음"}` }) + legend(pts.length) + chartTable(day) + `</section>`;
  h += `<section aria-labelledby="sh"><h3 id="sh">오늘 공연</h3>${day.shows.length ? showList(day) : "<p>누리집 일정에 오늘 공연이 없습니다.</p>"}</section>`;
  return h;
}
function showList(day) {
  return `<ul class="events">${day.shows.map((s) => `<li><a href="#event/${esc(s.event)}/${day.date}"><strong>${esc(s.title)}</strong><br><span class="muted">${esc(s.venue)} · ${s.times.join(", ")} 시작</span></a></li>`).join("")}</ul>`;
}

// ---------- 화면 2: 예보 달력 ----------
function viewCalendar() {
  const hours = []; for (let h = 8; h < 24; h++) hours.push(h);
  let h = `<h2>예보 달력</h2><p>오늘부터 ${D.fc.days.length}일, 정시 기준 예상 주차대수 등급입니다. 칸의 글자는 등급의 첫 글자입니다.</p>`;
  h += `<ul class="legend">${GRADES.slice().reverse().map(([r, n, a, c]) => `<li><span class="label ${c}">${a}</span> ${n}${r ? ` (${r * 100}% 이상)` : " (50% 미만)"}</li>`).join("")}</ul>`;
  h += `<div class="scroll" tabindex="0" role="region" aria-label="예보 달력 표, 옆으로 밀어 볼 수 있음"><table class="grid"><caption class="muted" style="text-align:left">날짜별 시간대 등급 (2,200대 기준)</caption><thead><tr><th scope="col">날짜</th>${hours.map((x) => `<th scope="col">${x}</th>`).join("")}</tr></thead><tbody>`;
  for (const d of D.fc.days) {
    const w = d.weather ? ` ${d.weather.rain ? "비" : ""}${d.weather.pop != null ? ` ${d.weather.pop}%` : ""}` : "";
    h += `<tr><th scope="row"><a href="#day/${d.date}">${dayLabel(d.date)}</a>${d.shows.length ? " ●" : ""}<br><span class="muted" style="font-size:11px">${d.shows.length ? "공연 " + d.shows.length : esc(d.type_ko)}${esc(w)}</span></th>`;
    for (const x of hours) { const v = d.mid[x * 6], g = grade(v); h += `<td class="${g[3]}" title="${x}시 ${g[1]} ${fmt(v)}대" aria-label="${x}시 ${g[1]}">${g[2]}</td>`; }
    h += `</tr>`;
  }
  h += `</tbody></table></div><p class="muted">● 공연이 있는 날. 날짜를 누르면 그날 곡선을 봅니다. 비와 %는 기상청 단기예보의 강수확률(화면에 보여 주기만 하고 수치에는 넣지 않습니다).</p>`;
  return h;
}
function viewDay(date) {
  const d = D.fc.days.find((x) => x.date === date);
  if (!d) return `<p>그 날짜의 예보가 없습니다. <a href="#calendar">예보 달력</a></p>`;
  let h = `<h2>${dayLabel(d.date)} ${esc(d.type_ko)} ${labelTag(d.label)}</h2>`;
  if (d.transit_advice) h += `<p class="advice" role="note"><strong>대중교통을 권합니다.</strong> “${TRANSIT}”</p>`;
  h += `<dl class="kv"><dt>차기 시작(70%)</dt><dd>${d.reach70 || "닿지 않음"}</dd><dt>가득 참(90%)</dt><dd>${d.reach90 || "닿지 않음"}</dd></dl>`;
  h += chart(d, { aria: `${d.date} 시간대별 예상 주차대수` }) + legend(false) + chartTable(d);
  h += d.shows.length ? `<h3>이날 공연</h3>${showList(d)}` : "";
  return h + `<p><a href="#calendar">← 예보 달력</a></p>`;
}

// ---------- 화면 3: 공연 목록과 공연 카드 ----------
function viewEvents() {
  const up = D.fc.days.filter((d) => d.shows.length);
  let h = `<h2>공연</h2><p>올림픽공원 누리집 일정에서 읽은 앞으로의 공연입니다(읽은 시각 ${tm(D.ev?.read_at)}${D.ev && D.ev.ok === false ? ", <strong>최근 읽기 실패: 지난 결과를 보여 줍니다</strong>" : ""}).</p>`;
  h += up.length ? up.map((d) => `<h3>${dayLabel(d.date)}</h3>${showList(d)}`).join("") : "<p>앞으로 14일 안에 일정이 없습니다.</p>";
  const unk = (D.ev?.events || []).filter((e) => e.status !== "ok");
  if (unk.length) h += `<h3>일정 미확인</h3><p class="muted">날짜나 시작 시각을 읽지 못해 카드를 만들지 않은 공연입니다.</p><ul>${unk.map((e) => `<li>${esc(e.title)} — “${esc(e.time_text)}”</li>`).join("")}</ul>`;
  return h;
}
function avgExit(rel) { const ps = D.fc.past_events; return Math.round(ps.reduce((a, p) => a + (p.exit_rel[String(rel)] || 0), 0) / ps.length); }
function viewEvent(id, date) {
  const ev = (D.ev?.events || []).find((e) => e.id === id);
  const day = D.fc.days.find((d) => d.date === date);
  if (!ev || !day) return `<p>공연을 찾지 못했습니다. <a href="#events">공연 목록</a></p>`;
  const show = ev.shows.find((s) => s.date === date);
  const start = toMin(show.times[show.times.length - 1]);
  const ps = D.fc.past_events, dur = D.fc.durations[ev.venue_key];
  const rngMin = (key) => [Math.min(...ps.map((p) => p[key])), Math.max(...ps.map((p) => p[key]))];
  let h = `<h2>${esc(ev.title)}</h2><p class="muted">${esc(ev.venue)} · ${dayLabel(date)} ${show.times.join(", ")} 시작 · <a href="${esc(ev.url)}">누리집 원문</a></p>`;
  h += `<p class="muted">누리집 원문 문장: “${esc(ev.time_text)}”${ev.manual_fix ? " (사람이 고친 값)" : ""}</p>`;
  if (day.uplift_start) {
    const r70 = rngMin("reach70_min"), r90 = rngMin("reach90_min");
    const pk = Math.round(ps.reduce((a, p) => a + p.exit_peak_min, 0) / ps.length / 10) * 10;
    const rush0 = Math.min(...ps.map((p) => p.rush_min[0])), rush1 = Math.max(...ps.map((p) => p.rush_min[1]));
    h += `<section class="card"><h3 style="margin-top:0">과거 비슷한 날의 범위 ${labelTag("표본 " + ps.length + "일")}</h3>`;
    h += `<p class="muted">2024년 7월 공연 주말(${ps.map((p) => p.date.slice(5) + " " + p.start + " 시작").join(", ")})의 실제 기록을 이 공연 시작 시각(${hm(start)})에 맞춰 옮긴 값입니다. 표본이 5일보다 적어 “예보”라고 부르지 않습니다.</p>`;
    const span = (r) => `${hm(start + r[0])}${r[0] !== r[1] ? "~" + hm(start + r[1]) : ""} (시작 ${-r[1]}${r[0] !== r[1] ? "~" + -r[0] : ""}분 전)`;
    h += `<dl class="kv"><dt>차기 시작(70%)</dt><dd>${span(r70)}</dd><dt>가득 참(90%)</dt><dd>${span(r90)}</dd>`;
    h += `<dt>출차가 몰리는 구간</dt><dd>${hm(start + rush0)}~${hm(start + rush1)}</dd>`;
    h += `<dt>가장 몰리는 10분</dt><dd>${hm(start + pk)} 전후 (과거 평균 ${avgExit(pk)}대)</dd></dl>`;
    h += `<h3>언제 나갈까 (공연 시작 기준 10분 출차 대수, 과거 평균)</h3><div class="scroll"><table><thead><tr><th scope="col">나가는 시각</th><th scope="col">같은 10분에 나가는 차</th></tr></thead><tbody>`;
    for (const [lab, off] of [["20분 일찍", pk - 20], ["가장 몰릴 때", pk], ["40분 늦게", pk + 40]]) h += `<tr><th scope="row">${lab} (${hm(start + off)})</th><td>${fmt(avgExit(off))}대</td></tr>`;
    h += `</tbody></table></div>`;
    h += `</section>`;
  } else {
    h += `<section class="card"><h3 style="margin-top:0">자료 부족 ${labelTag("공연 가산 없음")}</h3><p>이 공연장의 과거 공연일 주차 기록이 없어 공연 때문에 늘어나는 차를 계산하지 않았습니다. 아래 곡선은 같은 요일 유형의 기준 곡선입니다.</p>${dur ? `<p class="muted">소요시간 중앙값 ${dur.minutes}분(공연정보 ${dur.n}건), 종료 예정 ${hm(start + dur.minutes)}.</p>` : ""}</section>`;
  }
  if (day.transit_advice) h += `<p class="advice" role="note"><strong>대중교통을 권합니다.</strong> “${TRANSIT}”</p>`;
  h += `<h3>이날 시간대별 예상 ${labelTag(day.label)}</h3>` + chart(day, { aria: `${date} 시간대별 예상 주차대수` }) + legend(false) + chartTable(day);
  h += `<p><button type="button" id="copy">이 공연 카드 주소 복사</button> <span id="copied" role="status" aria-live="polite"></span></p>`;
  return h;
}

// ---------- 화면 4: 성적표 ----------
function viewScore() {
  const s = D.sc, v = s.validation, r = v.rule, bc = D.now?.baseline || {}, fe = s.full_vs_events;
  let h = `<h2>성적표</h2><p>공연 전날 22~24시에 저장해 둔 예보만 채점합니다. 저장한 파일은 고치지 않고, 저장 시각은 저장소 커밋 기록으로 남습니다. 잘 맞은 날만 고르지 않고 전부 싣습니다.</p>`;
  h += `<h3>저장해 둔 예보와 실측</h3>`;
  h += s.frozen.length ? `<div class="scroll"><table><thead><tr><th scope="col">날짜</th><th scope="col">저장 시각</th><th scope="col">상태</th><th scope="col">평균 오차</th><th scope="col">70% 도달 예보/실측</th><th scope="col">실측 기준</th></tr></thead><tbody>${s.frozen.map((f) => `<tr><th scope="row">${dayLabel(f.date)}</th><td>${tm(f.frozen_at)}</td><td>${esc(f.status)}</td><td>${f.mae != null ? fmt(f.mae) + "대 (" + f.n_points + "점)" : "-"}</td><td>${f.reach70_forecast || "없음"} / ${f.reach70_actual || "없음"}</td><td>${esc(f.actual_basis || "")}</td></tr>`).join("")}</tbody></table></div>` : `<p>아직 저장한 예보가 없습니다.</p>`;
  h += `<h3>과거 자료 검증 (2024년 7월, 하루씩 빼고 맞히기)</h3>`;
  h += `<p>06~24시 10분 단위 평균 절대 오차입니다. 전 주 같은 요일 값이 있는 ${r.n_compared}일로 견줬습니다.</p><div class="scroll"><table><thead><tr><th scope="col">방법</th><th scope="col">평균 오차</th></tr></thead><tbody><tr><th scope="row">이 서비스</th><td>${r.model}대</td></tr><tr><th scope="row">요일 유형 평균만</th><td>${r.typemean}대</td></tr><tr><th scope="row">직전 같은 요일 값</th><td>${r.prevweek}대</td></tr></tbody></table></div>`;
  const evr = v.rows.filter((x) => x.event);
  h += `<p>공연일 ${evr.length}일: ${evr.map((x) => `${x.date.slice(5)} 오차 ${x.model}대(요일 평균 ${x.typemean}대), 70% 도달 예보 ${x.reach70_model} / 실제 ${x.reach70_actual}`).join("; ")}.</p>`;
  h += `<p class="muted">한계: 공연일 표본이 2일뿐이고, 과거 공연 시작 시각은 그날 최대 시각 직후의 정시로 추정했습니다(그날 자료가 일부 들어갑니다). 그래서 공연일에는 “예보” 대신 “과거 비슷한 날의 범위”라고 씁니다. ${r.is_forecast ? "공연 없는 날은 두 기준 예측보다 오차가 작아 “예보”라고 씁니다." : ""}</p>`;
  h += `<h3>만차 기록과 공연 날짜 (${fe.period[0]}~${fe.period[1]})</h3><div class="scroll"><table><thead><tr><th scope="col"></th><th scope="col">만차 기록 있음</th><th scope="col">없음</th></tr></thead><tbody><tr><th scope="row">영문 공연정보에 공연이 있는 날</th><td>${fe.table.perf_full}</td><td>${fe.table.perf_notfull}</td></tr><tr><th scope="row">없는 날</th><td>${fe.table.noperf_full}</td><td>${fe.table.noperf_notfull}</td></tr></tbody></table></div>`;
  h += `<p class="muted">만차가 찍힌 ${fe.full_days}일 중 영문 공연정보의 공연 날짜와 겹친 날은 ${fe.table.perf_full}일입니다. 영문 공연정보에는 이 기간 공연 날짜가 ${fe.perf_days}일뿐이라(누리집 일정보다 훨씬 적다) 이 표로는 “공연일에 만차가 나는가”를 판단할 수 없습니다. 결론 없음으로 둡니다.</p>`;
  h += `<h3>실시간 값의 기준선 확인</h3><dl class="kv"><dt>새벽(03~05시) 최저값</dt><dd>${Object.entries(bc.nights || {}).map(([d, x]) => `${d.slice(5)} ${fmt(x)}대`).join(", ") || "없음"}</dd><dt>2024년 7월 04시 평균</dt><dd>${fmt(bc.night_ref_2024_07)}대</dd><dt>아침 증가분(07→11시)</dt><dd>${Object.entries(bc.morning || {}).map(([d, x]) => `${d.slice(5)} ${fmt(x.increase)}대 (2024년 7월 같은 요일 유형 ${fmt(x.ref_2024_07)}대)`).join(", ") || "없음"}</dd><dt>판정</dt><dd>${bc.confirmed ? "확인됨: 보정값 사용" : "확인 전: 원값만 표시"}</dd></dl>`;
  h += `<p class="muted">확인 기준: 밤이 둘 이상 쌓이고 새벽 최저값 차이가 5% 이내, 아침 증가분이 2024년 7월 같은 요일 유형의 0.5~2배. 둘 다 맞으면 “원값 − 새벽 최저값 + 2024년 7월 04시 평균”을 보정값으로 씁니다.</p>`;
  h += `<h3>계산 방법</h3><ul><li>동시 주차: 입출차 기록 ${fmt(s.trips.n)}건(2024년 7월)에서 10분마다 “들어와 있고 아직 안 나간 차”를 셉니다. 10분 안에 나간 차가 ${s.trips.short_pct}%라 입차 수를 그대로 쓰지 않습니다.</li><li>예보 = 요일 유형별(평일, 토요일, 일요일·공휴일) 기준 곡선 + 공연 가산. 가산은 2024-07-20·21 이틀의 곡선에서 기준 곡선을 뺀 값을 공연 시작 시각에 맞춰 옮깁니다. KSPO DOME 공연일에만 넣습니다(다른 공연장은 표본이 없습니다). 2,200대에서 자릅니다.</li><li>낮게·높게: 공연일 이틀의 가산 중 작은 값과 큰 값.</li><li>차기 시작·가득 참: 예보 가운데 값이 70%와 90%에 닿는 시각. 2024-07-20·21에 잰 문턱입니다.</li><li>출차가 몰리는 구간: 18시 뒤 10분 출차가 그날 저녁 최대의 60% 이상인 구간.</li><li>월별 보정: 11월/7월 비율 ${s.monthly.factor_vs_2024_07}배(월별주차현황 2024년). 실측으로 확인하기 전이라 ${s.monthly.applied ? "적용합니다" : "적용하지 않습니다"}.</li><li>날씨: 기상청 단기예보를 달력에 보여 주기만 합니다(2025년 연계 데이터를 받지 못해 비의 영향을 계산하지 못했습니다).</li></ul>`;
  const src = s.sources;
  h += `<h3>데이터 출처와 마지막 갱신</h3><div class="scroll"><table><thead><tr><th scope="col">데이터</th><th scope="col">쓰는 곳</th><th scope="col">상태</th></tr></thead><tbody>
<tr><th scope="row">한국체육산업개발 실시간 주차현황(15168686)</th><td>지금, 성적표 실측</td><td>${src.realtime_points}건, 마지막 ${tm(src.realtime_last)}</td></tr>
<tr><th scope="row">올림픽공원 입출차 정보 2024년 7월(15138735)</th><td>기준 곡선, 공연 가산, 출차 구간, 검증</td><td>${fmt(s.trips.n)}건</td></tr>
<tr><th scope="row">주차장 혼잡도 정보(15164156)</th><td>만차 기록 검증</td><td>만차 ${fe.full_days}일</td></tr>
<tr><th scope="row">월별주차현황(15131671)</th><td>월별 보정 후보</td><td>2023~2025년</td></tr>
<tr><th scope="row">영문 공연정보(15149169)</th><td>과거 공연 날짜</td><td>2026-10-17까지</td></tr>
<tr><th scope="row">올림픽공원 공연정보(문화공공데이터광장, 3037877)</th><td>공연장별 소요시간</td><td>2,502건</td></tr>
<tr><th scope="row">올림픽공원 일정안내(누리집 공개 화면)</th><td>앞으로의 공연 날짜와 시각</td><td>${src.events.ok ? "읽음 " + tm(src.events.read_at) : "실패 " + tm(src.events.failed_at)}</td></tr>
<tr><th scope="row">기상청 단기예보(15084084)</th><td>달력의 강수확률</td><td>${src.weather.ok ? "발표 " + esc(src.weather.base) : "없음(" + esc(src.weather.reason) + ")"}</td></tr>
<tr><th scope="row">2025 입출차·공연·날씨 연계 데이터(15164822)</th><td>받으면 1년치 학습과 날씨 반영</td><td>${src.kcisa_675.ok ? "받음" : "응답 없음(HTTP " + esc(src.kcisa_675.last_status) + ")"}</td></tr>
</tbody></table></div>`;
  h += `<details><summary>최근 외부 호출 기록 (키는 가림)</summary><div class="scroll"><table><thead><tr><th scope="col">시각</th><th scope="col">주소</th><th scope="col">결과</th></tr></thead><tbody>${(D.calls || []).slice(0, 30).map((c) => `<tr><td>${tm(c.at)}</td><td style="word-break:break-all">${esc(c.url)}</td><td>${esc(c.status)} · ${fmt(c.bytes)}B · ${c.seconds}초</td></tr>`).join("")}</tbody></table></div></details>`;
  return h;
}

// ---------- 길 찾기 ----------
function route() {
  if (!D.fc) return;
  const [tab, a, b] = (location.hash.slice(1) || "now").split("/");
  const views = { now: viewNow, calendar: viewCalendar, events: viewEvents, score: viewScore, day: () => viewDay(a), event: () => viewEvent(a, b) };
  $main.innerHTML = (views[tab] || viewNow)();
  const cur = { day: "calendar", event: "events" }[tab] || (views[tab] ? tab : "now");
  document.querySelectorAll("nav a").forEach((n) => (n.dataset.tab === cur ? n.setAttribute("aria-current", "page") : n.removeAttribute("aria-current")));
  const titles = { now: "지금", calendar: "예보 달력", events: "공연", score: "성적표", day: "날짜별 예보", event: "공연 카드" };
  document.title = `${titles[tab] || "지금"} - 올팍 주차예보`;
  const copy = document.getElementById("copy");
  if (copy) copy.onclick = async () => { let ok = true; try { await navigator.clipboard.writeText(location.href); } catch { ok = false; } document.getElementById("copied").textContent = ok ? "주소를 복사했습니다." : "복사하지 못했습니다. 주소창의 주소를 복사해 주세요."; };
  if (!demo) { $main.focus({ preventScroll: true }); window.scrollTo(0, 0); }
}
window.addEventListener("hashchange", route);

// ---------- ?demo=1 자동 시연 (녹화용). &step=N이면 그 장면에서 멈춘다 ----------
const params = new URLSearchParams(location.search);
const demo = params.get("demo") === "1";
function demoSteps() {
  const ev = D.fc.days.find((d) => d.date >= todayIso() && d.shows.some((s) => s.venue_key === "KSPO DOME"));
  const s = ev && ev.shows.find((x) => x.venue_key === "KSPO DOME");
  return [
    ["now", "지금: 실시간 주차대수와 오늘 예보 곡선, 차기 시작 시각과 가득 차는 시각"],
    ["calendar", "예보 달력: 14일 동안 시간대별 여유·보통·혼잡·만차를 글자와 색으로"],
    [s ? `event/${s.event}/${ev.date}` : "events", "공연 카드: 몇 시에 차는지, 공연 뒤 언제 출차가 몰리는지"],
    ["score", "성적표: 공연 전에 저장한 예보만 실측과 견주고, 전부 공개"],
  ];
}
async function runDemo() {
  await load();
  const cap = document.getElementById("demo-caption");
  cap.hidden = false;
  const steps = demoSteps();
  const only = params.get("step");
  const show = (i) => { location.hash = steps[i][0]; cap.textContent = `${i + 1}/${steps.length} ${steps[i][1]}`; };
  if (only != null) { show(Number(only)); return; }
  for (let i = 0; ; i = (i + 1) % steps.length) {
    show(i);
    await new Promise((r) => setTimeout(r, 2500));
    window.scrollTo({ top: document.body.scrollHeight / 3, behavior: "smooth" });
    await new Promise((r) => setTimeout(r, 3500));
  }
}
demo ? runDemo() : load();
