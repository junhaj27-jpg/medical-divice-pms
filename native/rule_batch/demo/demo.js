/* global createRuleBatch */
"use strict";

const byId = id => document.getElementById(id);
const market = byId("market"), baseline = byId("baseline"), proposed = byId("proposed");
const labels = {
    KR: "한국", US: "미국", DE: "독일", REPORT: "보고 필요", NO_MATCH: "적용 대상 아님",
    HOLD: "판단 보류", unsupported: "지원 범위 밖", rule_match: "규칙 조건 충족",
    scope_mismatch: "적용 범위·조건 불일치", source_unverified: "근거 확인 필요",
    missing_input: "필수 입력 누락", date_mismatch: "기산일 불일치",
    calculation_unverified: "기한 또는 휴일 확인 필요", unsupported_method: "계산 방식 미지원",
    unsupported_timezone: "시간대 미지원", unsupported_timestamp: "시각 기산점 미지원",
    decision_changed: "보고 판단 변경", earlier: "기한 앞당김", later: "기한 늦어짐",
    time_changed: "마감 시각 변경", deadline_added: "기한 추가", deadline_removed: "기한 제거",
    review_required: "추가 확인 필요", unchanged: "변경 없음",
};

function options(select, values, chosen) {
    select.replaceChildren(...values.map(([value, text]) => new Option(text, value)));
    select.value = chosen;
}

function showResult(result) {
    return [
        labels[result.decision] + " · " + labels[result.reason],
        result.rule_id + " · v" + result.version,
        "기산일 " + (result.basis_date ?? "—"),
        "마감 " + (result.due_at ?? "—"),
    ].join("\n");
}

async function start() {
    const [engine, fixtures] = await Promise.all([
        createRuleBatch(),
        fetch("examples.json").then(response => {
            if (!response.ok) throw new Error("examples");
            return response.json();
        }),
    ]);
    const samples = Object.fromEntries(fixtures.markets.map(sample => [sample.market, sample]));
    function run() {
        const sample = samples[market.value];
        const rules = [baseline.value, proposed.value].map(index => sample.rules[Number(index)]);
        const result = JSON.parse(engine.runJson(JSON.stringify({
            schema_version: 1, market: sample.market, rules, cases: sample.cases,
        })));
        if (result.error) {
            byId("status").textContent = "예시 검증 오류 · " + result.error.code;
            byId("rows").replaceChildren();
            return;
        }
        byId("rows").replaceChildren(...result.results.map(row => {
            const tr = document.createElement("tr");
            const cells = [
                row.case_id, showResult(row.baseline), showResult(row.proposed),
                row.changes.map(flag => labels[flag]).join(" · ") + "\n" + (row.delta_days ?? "—"),
            ];
            cells.forEach((value, index) => {
                const cell = document.createElement(index ? "td" : "th");
                if (!index) cell.scope = "row";
                cell.textContent = value;
                tr.append(cell);
            });
            return tr;
        }));
    }
    function chooseMarket() {
        const versions = samples[market.value].rules.map((rule, index) => [
            String(index), rule.id + " · v" + rule.version,
        ]);
        options(baseline, versions, "0");
        options(proposed, versions, "1");
        run();
    }
    options(market, Object.keys(samples).map(code => [code, labels[code]]), fixtures.markets[0].market);
    market.addEventListener("change", chooseMarket);
    baseline.addEventListener("change", run);
    proposed.addEventListener("change", run);
    byId("run").addEventListener("click", run);
    byId("controls").disabled = false;
    chooseMarket();
    byId("status").textContent = "비교 준비 완료 · 이 탭에서 연결을 끊어도 다시 계산할 수 있습니다.";
    if ("serviceWorker" in navigator) {
        try {
            await navigator.serviceWorker.register("sw.js");
            await navigator.serviceWorker.ready;
            byId("status").textContent = "오프라인 준비 완료 · 연결을 끊고 페이지를 다시 열 수 있습니다.";
        } catch {
            byId("status").textContent = "이 탭에서 오프라인 비교가 가능합니다. 오프라인 재열기용 저장은 실패했습니다.";
        }
    }
}

start().catch(() => { byId("status").textContent = "데모 자산을 읽지 못했습니다. 빌드된 폴더를 로컬 HTTP 서버로 여세요."; });
