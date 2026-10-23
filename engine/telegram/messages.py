"""Telegram message texts (HTML parse mode). Pure functions: data in, text out."""
from html import escape
from typing import Any, Dict, List, Optional

DISCLAIMER = "<i>Analisis teknikal otomatis, bukan ajakan beli/jual. Keputusan & risiko di tangan Anda.</i>"

MODE_LABELS = {"NORMAL": "Normal", "CAUTIOUS": "Waspada", "BEARISH": "Bearish", "CRASH": "Krisis"}
VERDICT_LABELS = {
    "STRONG_BULLISH": "Strong bullish", "MILD_BULLISH": "Mild bullish", "NEUTRAL": "Netral",
    "MILD_BEARISH": "Mild bearish", "STRONG_BEARISH": "Strong bearish",
}
POSITION_ICONS = {
    "BELOW_STOP": "🔴", "TESTING_SUPPORT": "🟡", "IN_ZONE": "✅", "ABOVE_ZONE": "⏫", "AT_TP1": "🎯", "AT_TP2": "🎯",
}
FLAG_SHORT = {"tight_room": "ruang naik sempit", "wide_stop": "stop lebar", "market_entry": "entry harga pasar",
              "projected_tp1": "TP1 proyeksi", "too_volatile": "terlalu volatil"}
STATUS_ICONS = {"LAYAK": "✅ LAYAK", "TUNGGU": "⏳ TUNGGU", "HINDARI": "⛔ HINDARI"}


def _status(r: Dict[str, Any]) -> str:
    st = (r.get("action") or {}).get("status")
    return f" · {STATUS_ICONS[st]}" if st in STATUS_ICONS else ""


def status_counts(rows: List[Dict[str, Any]]) -> str:
    counts = {k: sum(1 for r in rows if (r.get("action") or {}).get("status") == k) for k in STATUS_ICONS}
    return " · ".join(f"{n} {k}" for k, n in counts.items()) if any(counts.values()) else ""

COMMANDS = [
    {"command": "top10", "description": "10 saham skor tertinggi + rencananya"},
    {"command": "cek", "description": "Rencana satu saham, contoh: /cek BBCA"},
    {"command": "rencana", "description": "Rencana terakhir untuk sesi berikutnya"},
    {"command": "tengahhari", "description": "Posisi harga vs rencana sekarang"},
    {"command": "pasar", "description": "Kondisi pasar & jam bursa"},
    {"command": "rekam", "description": "Rekam jejak prediksi 7 hari terakhir"},
    {"command": "bantuan", "description": "Daftar perintah"},
]


def num(v: Optional[float], market: str = "IDX") -> str:
    if v is None:
        return "-"
    v = float(v)
    if market == "US":
        return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{v:,.0f}".replace(",", ".") if abs(v) >= 100 else f"{v:,.2f}".replace(".", ",")


def dec(v: Optional[float], digits: int = 1) -> str:
    return "-" if v is None else f"{float(v):.{digits}f}".replace(".", ",")


def signed(v: Optional[float], suffix: str = "%", digits: int = 1) -> str:
    return "-" if v is None else f"{'+' if float(v) >= 0 else ''}{dec(v, digits)}{suffix}"


def code(ticker: str) -> str:
    return escape(str(ticker).replace(".JK", ""))


def _plan_line(lv: Dict[str, Any], market: str) -> str:
    flags = [FLAG_SHORT[f] for f in (lv.get("flags") or []) if f in FLAG_SHORT]
    rr = lv.get("risk_reward_ratio")
    rec = lv.get("recommended_entry")
    line = (f"Beli {num(lv.get('entry_low'), market)}–{num(lv.get('entry_high'), market)}"
            + (f" (saran {num(rec, market)})" if rec else "")
            + f" · TP1 {num(lv.get('target_tp1'), market)} · CL {num(lv.get('stop_loss'), market)}")
    if rr is not None:
        line += f" · R:R {dec(rr)}"
    if flags:
        line += f" · ⚠ {', '.join(flags)}"
    return line


def _mode_warning(mode: str) -> str:
    if mode == "CRASH":
        return "⛔ <b>Pasar krisis</b> — utamakan jaga modal; daftar ini peringkat relatif, bukan sinyal beli."
    if mode == "BEARISH":
        return "🐻 <b>Pasar bearish</b> — hanya saham terkuat yang layak dipantau; porsi kecil."
    if mode == "CAUTIOUS":
        return "⚠️ Pasar waspada — indeks sedang melemah."
    return ""


def daily_plan(rows: List[Dict[str, Any]], market: str, as_of: str, next_label: str, mode: str) -> str:
    lines = [f"📋 <b>Rencana SAHAM {escape(market)} — {escape(next_label)}</b>",
             f"Dari penutupan final {escape(as_of)} · Pasar: {MODE_LABELS.get(mode, mode)}"]
    warn = _mode_warning(mode)
    if warn:
        lines.append(warn)
    counts = status_counts(rows)
    if counts:
        lines.append(f"Status: {counts}" + ("" if "LAYAK" in counts and not counts.startswith("0 LAYAK") else
                                             " — belum ada setup yang layak dieksekusi"))
    lines.append("")
    for i, r in enumerate(rows, 1):
        lv = r.get("levels") or {}
        verdict = VERDICT_LABELS.get(r.get("verdict"), r.get("verdict") or "-")
        lines.append(f"{i}. <b>{code(r['ticker'])}</b> {num(r.get('price'), market)} · skor {r.get('score')} · {verdict}{_status(r)}")
        if lv:
            lines.append(f"    {_plan_line(lv, market)}")
    lines += ["", "<i>Panduan saat bursa buka (pagi & sesi 2): di atas zona → jangan dikejar · "
                  "di zona → sesuai rencana, pasang CL · di bawah CL → rencana batal.</i>", DISCLAIMER]
    return "\n".join(lines)


def midday(rows: List[Dict[str, Any]], market: str, date: str, session_note: str) -> str:
    lines = [f"☕ <b>Cek Tengah Hari {escape(market)}</b> · {escape(date)}", escape(session_note), ""]
    if not rows:
        lines.append("Harga hari ini belum tersedia dari sumber data.")
    for r in rows:
        icon = POSITION_ICONS.get(r.get("status"), "•")
        extra = " · sempat sentuh CL" if r.get("touched_stop") and r.get("status") != "BELOW_STOP" else ""
        lines.append(f"{icon} <b>{code(r['ticker'])}</b> {num(r.get('price'), market)} — {escape(r.get('label', ''))}{extra}")
        lines.append(f"    zona {num(r.get('entry_low'), market)}–{num(r.get('entry_high'), market)} · "
                     f"CL {num(r.get('stop_loss'), market)} · TP1 {num(r.get('target_tp1'), market)}")
    lines += ["", "<i>Sesi 2 bisa dibuka melompat bila ada berita selama istirahat — cek harga pembukaan dulu.</i>", DISCLAIMER]
    return "\n".join(lines)


ALERT_TITLES = {
    "entry_zone": ("🟢", "mencapai harga saran beli"),
    "tp": ("🎯", "menyentuh TP1"),
    "stop": ("🔴", "menyentuh cut loss"),
}


def alert(kind: str, ticker: str, market: str, live: Dict[str, Any], lv: Dict[str, Any]) -> str:
    icon, title = ALERT_TITLES[kind]
    lines = [f"{icon} <b>{code(ticker)} {title}</b> — harga {num(live.get('price'), market)}",
             f"Rencana: {_plan_line(lv, market)}"]
    if kind == "entry_zone":
        lines.append(f"Harga saran {num(lv.get('recommended_entry'), market)} tercapai — sesuai rencana bila ingin "
                     "masuk; pasang cut loss sejak awal.")
    elif kind == "tp":
        lines.append("Punya posisi: jual separuh, naikkan cut loss ke harga beli, sisanya incar TP2. Belum punya: jangan dikejar.")
    else:
        lines.append("Rencana batal. Punya posisi: jalankan cut loss.")
    lines.append("<i>Data tertunda ±15 menit.</i>")
    return "\n".join(lines)


def weekly(summary: Dict[str, Any], dates: List[str], market: str) -> str:
    s = summary
    lines = [f"📊 <b>Rekam Jejak Mingguan {escape(market)}</b>",
             f"Rencana tanggal {escape(dates[-1]) if dates else '-'} s/d {escape(dates[0]) if dates else '-'} "
             f"({len(dates)} hari, {s.get('total_predictions', 0)} rencana)"]
    if not s.get("total_predictions"):
        lines += ["", "Tidak ada sinyal beli yang dicatat minggu ini (pasar lemah/krisis).", DISCLAIMER]
        return "\n".join(lines)
    tp = (s.get("hit_tp1_count") or 0) + (s.get("hit_tp2_count") or 0)
    unfilled = (s.get("not_filled_count") or 0) + (s.get("cancelled_count") or 0)
    lines += [
        "",
        f"🎯 Kena TP: {tp} · 🔴 Cut loss: {s.get('stopped_out_count', 0)} · ⌛ Habis waktu: {s.get('expired_count', 0)}",
        f"⏳ Berjalan: {s.get('in_progress_count', 0)} · 🕓 Menunggu zona: {s.get('waiting_entry_count', 0)} · "
        f"⊘ Tak sempat dibeli: {unfilled}",
        f"Kena TP dulu: <b>{dec(s.get('win_rate_pct')) + '%' if s.get('win_rate_pct') is not None else '-'}</b> dari yang selesai",
    ]
    if s.get("avg_r") is not None:
        lines.append(f"Rata-rata hasil: <b>{signed(s.get('avg_r'), 'R', 2)}</b> (≈ {signed(s.get('avg_return_pct'))})")
    elif s.get("avg_return_pct") is not None:
        lines.append(f"Rata-rata hasil: <b>{signed(s.get('avg_return_pct'))}</b>")
    if s.get("avg_excess_return_pct") is not None:
        lines.append(f"vs indeks: {signed(s.get('avg_excess_return_pct'))}")
    lines += ["", "<i>Tanpa biaya transaksi. Sampel mingguan kecil — lihat tab Uji Historis untuk gambaran besar.</i>"]
    return "\n".join(lines)


def stock(a: Dict[str, Any], market: str) -> str:
    tech = a.get("technical") or {}
    comp = a.get("composite") or {}
    lv = comp.get("levels") or {}
    verdict = VERDICT_LABELS.get(comp.get("verdict"), comp.get("verdict") or "-")
    lines = [f"🔎 <b>{code(a.get('ticker', ''))}</b> {num(tech.get('price'), market)} ({signed(tech.get('change_pct'))})",
             f"Skor {comp.get('score', '-')} · {verdict} · Pasar: {MODE_LABELS.get(comp.get('market_mode'), comp.get('market_mode') or '-')}"]
    if lv:
        lines.append(_plan_line(lv, market))
        if lv.get("as_of"):
            lines.append(f"<i>Rencana dari penutupan {escape(str(lv['as_of']))}</i>")
        live = lv.get("live")
        if live:
            lines.append(f"{POSITION_ICONS.get(live.get('status'), '•')} Sekarang: {escape(live.get('label', ''))}")
    action = comp.get("action") or {}
    if action.get("status") in STATUS_ICONS:
        lines.append(f"Status: {STATUS_ICONS[action['status']]}")
        lines += [f"  – {escape(str(x))}" for x in (action.get("reasons") or [])[:3]]
    reasons = [str(x) for x in (comp.get("reasons") or [])][:4]
    if reasons:
        lines.append("")
        lines += [f"• {escape(x)}" for x in reasons]
    lines += ["", DISCLAIMER]
    return "\n".join(lines)


def top10(rows: List[Dict[str, Any]], market: str, mode: str) -> str:
    lines = [f"🏆 <b>Top 10 {escape(market)}</b> · Pasar: {MODE_LABELS.get(mode, mode)}"]
    warn = _mode_warning(mode)
    if warn:
        lines.append(warn)
    lines.append("")
    for i, r in enumerate(rows, 1):
        lv = r.get("levels") or {}
        live = lv.get("live") or {}
        icon = POSITION_ICONS.get(live.get("status"), "")
        lines.append(f"{i}. <b>{code(r['ticker'])}</b> {num(r.get('price'), market)} · skor {r.get('score')}{_status(r)} {icon}")
        if lv:
            lines.append(f"    {_plan_line(lv, market)}")
    lines += ["", "Detail: /cek KODE", DISCLAIMER]
    return "\n".join(lines)


def market_status(sessions: Dict[str, Dict[str, Any]], modes: Dict[str, str]) -> str:
    lines = ["🌐 <b>Kondisi Pasar</b>"]
    for m, s in sessions.items():
        lines.append(f"<b>{escape(m)}</b>: {escape(s.get('label', '-'))} · mode {MODE_LABELS.get(modes.get(m), modes.get(m) or '-')}")
    return "\n".join(lines)


def help_text() -> str:
    lines = ["🤖 <b>Bot SAHAM</b> — perintah:"]
    lines += [f"/{c['command']} — {escape(c['description'])}" for c in COMMANDS]
    lines += ["", "Pesan otomatis: rencana setelah bursa tutup, cek tengah hari, peringatan zona beli/TP/cut loss, "
                  "rekam jejak setiap Jumat.", DISCLAIMER]
    return "\n".join(lines)
