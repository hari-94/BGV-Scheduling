/**
 * ENG sheet update -- Office Script for "Daily Tasks Ops Departments.xlsx",
 * tab "RQS-ENG-Runners". Run by the Power Automate flow "BGV ENG sheet" with
 * the text file the office PC drops into "App Outbox" after a Push
 * (eng_sheet.py builds it).
 *
 * Writes ONLY: the date/time at the top (B2), the AM houseperson names
 * (column E, rows of the "AM Housepersons" block, by HSP number and the
 * "Hsp Lead Am" row), the PM houseperson names (column E of the "PM
 * Housepersons" block the same way, its lead row being whichever says "Hsp
 * Lead"), and the RQS names + Full Clean rooms (columns F and G)
 * under the BLD 1 / BLD 2 / BLD 3 labels. Everything else belongs to other
 * teams and is not touched. Rows are found by their labels, not fixed row
 * numbers, so a row added to the sheet doesn't send names to the wrong place.
 */
function main(workbook: ExcelScript.Workbook, payload: string) {
  const p = JSON.parse(payload) as {
    title: string;
    housepersons: { [slot: string]: string[] };
    housepersons_pm?: { [slot: string]: string[] };
    rqs: { [bld: string]: string[][] };
  };
  const ws = workbook.getWorksheet("RQS-ENG-Runners");
  if (!ws) throw new Error("Tab 'RQS-ENG-Runners' not found");

  const vals = ws.getRange("A1:K80").getValues();
  const cell = (r: number, c: number) => String(vals[r][c] ?? "").trim();   // r, c are 0-based
  const B = 1, C = 2, D = 3, E = 4, F = 5, G = 6;
  const find = (col: number, test: (s: string) => boolean, from = 0) => {
    for (let r = from; r < vals.length; r++) if (test(cell(r, col))) return r;
    return -1;
  };

  // 1. date and time at the top
  ws.getRange("B2").setValue(p.title);

  // 2. AM housepersons: between "AM Housepersons" and "PM Housepersons"
  const am = find(B, s => /^am housepersons/i.test(s));
  const pm = find(B, s => /^pm housepersons/i.test(s), am + 1);
  if (am >= 0 && pm > am) {
    for (let r = am + 1; r < pm; r++) {
      const m = cell(r, D).match(/^hsp\s*(\d)/i);
      let slot = m ? `HSP ${m[1]}` : "";
      if (!slot && /hsp lead am/i.test(cell(r, C))) slot = "LEAD";
      if (slot && p.housepersons[slot] !== undefined) {
        ws.getCell(r, E).setValue(p.housepersons[slot].join(" / "));
      }
    }
  }

  // 2b. PM housepersons: from "PM Housepersons" down to the next label in
  // column B. Each slot is written once, so a block below that also has HSP
  // rows can't be reached even if the sheet has no label between them. A
  // payload from before the PM names were sent has none, and leaves it alone.
  const pmNames = p.housepersons_pm;
  if (pm >= 0 && pmNames) {
    let stop = vals.length;
    for (let r = pm + 1; r < vals.length; r++) if (cell(r, B)) { stop = r; break; }
    const done: { [slot: string]: boolean } = {};
    for (let r = pm + 1; r < stop; r++) {
      const m = cell(r, D).match(/^hsp\s*(\d)/i);
      let slot = m ? `HSP ${m[1]}` : "";
      if (!slot && /hsp lead/i.test(cell(r, C))) slot = "LEAD";
      if (slot && !done[slot] && pmNames[slot] !== undefined) {
        ws.getCell(r, E).setValue(pmNames[slot].join(" / "));
        done[slot] = true;
      }
    }
  }

  // 3. RQS and rooms under each building label in column G
  const head = find(F, s => /^housekeeping rqs/i.test(s));
  let end = find(B, s => /^front desk/i.test(s), head + 1);
  if (end < 0) end = vals.length;
  const labels: { row: number; bld: string }[] = [];
  for (let r = head + 1; r < end; r++) {
    const m = cell(r, G).match(/^bld\s*(\d)$/i);
    if (m) labels.push({ row: r, bld: m[1] });
  }
  labels.forEach((lab, i) => {
    const first = lab.row + 1;
    const last = (i + 1 < labels.length ? labels[i + 1].row : end) - 1;
    const rows = last - first + 1;
    if (rows <= 0) return;
    const entries = (p.rqs[lab.bld] || []).map(e => [e[0], e[1]]);
    if (entries.length > rows) {            // more RQS than rows: the rest share the last row
      const extra = entries.splice(rows - 1);
      entries.push([extra.map(e => e[0]).join(" / "), extra.map(e => `${e[0]}: ${e[1]}`).join("   ")]);
    }
    for (let k = 0; k < rows; k++) {
      ws.getCell(first + k, F).setValue(k < entries.length ? entries[k][0] : "");
      ws.getCell(first + k, G).setValue(k < entries.length ? entries[k][1] : "");
    }
  });
}
