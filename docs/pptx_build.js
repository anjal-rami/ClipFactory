// ClipFactory — 7-slide challenge deck (fully editable, per required format)
const pptxgen = require("pptxgenjs");

const p = new pptxgen();
p.layout = "LAYOUT_WIDE";               // 13.33 x 7.5"
p.author = "Anjal Rami";
p.title = "ClipFactory — AI Video Pipeline for the Qoneqt Global Feed";

const W = 13.33, M = 0.6, CW = W - 2 * M;
const BG = "17112E", CARD = "1D1738", PRIMARY = "7C5CFF", PRIMARY_DK = "5A48C2";
const ACCENT = "FFC857", TEXT = "EAE6FF", MUTED = "A99EDE", LINE = "2E2557";
const F = "Segoe UI";

const T = (s, t, o) => s.addText(t, Object.assign({ fontFace: F, margin: 0 }, o));
const title = (s, t) => T(s, t, { x: M, y: 0.42, w: CW, h: 0.75, fontSize: 36, bold: true, color: TEXT });
const footer = (s, n) => {
  T(s, "ClipFactory", { x: M, y: 7.08, w: 2, h: 0.3, fontSize: 10, color: MUTED });
  T(s, String(n), { x: W - M - 0.6, y: 7.08, w: 0.6, h: 0.3, fontSize: 10, color: MUTED, align: "right" });
};
const chip = (s, x, y, n) => {
  s.addShape(p.shapes.ROUNDED_RECTANGLE, { x, y, w: 0.62, h: 0.62, fill: { color: PRIMARY }, rectRadius: 0.12 });
  T(s, n, { x, y, w: 0.62, h: 0.62, fontSize: 19, bold: true, color: "FFFFFF", align: "center", valign: "middle" });
};
const bu = () => ({ code: "25B8", indent: 12 });

// ---------- Slide 1 · Title ----------
let s = p.addSlide(); s.background = { color: BG };
T(s, [{ text: "Clip", options: { color: TEXT } }, { text: "Factory", options: { color: PRIMARY } }],
  { x: M, y: 1.7, w: CW, h: 1.1, fontSize: 60, bold: true });
T(s, "AI Video Pipeline for the Qoneqt Global Feed", { x: M, y: 2.95, w: CW, h: 0.55, fontSize: 24, color: TEXT });
T(s, "Qoneqt × CTRL FREAK — AI Challenge", { x: M, y: 3.6, w: CW, h: 0.4, fontSize: 15, color: MUTED });
T(s, [
  { text: "Team Name & ID:  ", options: { color: MUTED, breakLine: true } },
  { text: "[Team Name & ID]", options: { color: TEXT, italic: true, breakLine: true } },
  { text: "", options: { breakLine: true } },
  { text: "College Name:  ", options: { color: MUTED, breakLine: true } },
  { text: "[College Name]", options: { color: TEXT, italic: true } },
], { x: M, y: 5.15, w: 6.5, h: 1.7, fontSize: 16 });
T(s, "Topic in  →  script, visuals, voice, edit  →  publish-ready 9:16 video", { x: M, y: 4.55, w: CW, h: 0.4, fontSize: 13, color: PRIMARY });

// ---------- Slide 2 · Problem + Existing Gap ----------
s = p.addSlide(); s.background = { color: BG };
title(s, "The Problem & the Gap");
const probs = [
  ["Constant video demand", "Communities and creators must publish short-form video every day to stay visible."],
  ["Production is the bottleneck", "Scripting, shooting and editing take hours per video — plus paid tools and editing skill."],
  ["Current AI tools are one-off", "They generate a single clip or a draft; a human still assembles, formats and publishes."],
  ["The gap", "No repeatable pipeline that ends with a platform-formatted, publish-ready video."],
];
probs.forEach((r, i) => {
  const y = 1.45 + i * 1.32;
  T(s, r[0], { x: M, y, w: 8.6, h: 0.4, fontSize: 17, bold: true, color: i === 3 ? ACCENT : TEXT });
  T(s, r[1], { x: M, y: y + 0.42, w: 8.6, h: 0.62, fontSize: 13.5, color: MUTED });
  if (i < 3) s.addShape(p.shapes.LINE, { x: M, y: y + 1.16, w: 8.6, h: 0, line: { color: LINE, width: 0.75 } });
});
s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: 9.9, y: 1.6, w: 2.85, h: 3.9, fill: { color: CARD }, rectRadius: 0.14 });
T(s, "24/7", { x: 9.9, y: 2.15, w: 2.85, h: 1.2, fontSize: 66, bold: true, color: PRIMARY, align: "center" });
T(s, "content expectations —\nbut production capacity\nis measured in hours", { x: 10.05, y: 3.55, w: 2.55, h: 1.7, fontSize: 12.5, color: MUTED, align: "center" });
footer(s, 2);

// ---------- Slide 3 · Proposed Solution ----------
s = p.addSlide(); s.background = { color: BG };
title(s, "The Solution");
T(s, [
  { text: "Type any topic — get a publish-ready 9:16 video in ", options: { color: TEXT } },
  { text: "about 3 minutes.", options: { color: ACCENT } },
], { x: M, y: 1.35, w: CW, h: 1.15, fontSize: 26, bold: true });
const flow = ["Topic", "Script", "Visuals", "Voice", "Video", "Qoneqt"];
flow.forEach((t, i) => {
  const x = M + i * 2.07;
  s.addShape(p.shapes.ROUNDED_RECTANGLE, { x, y: 2.85, w: 1.75, h: 0.72, fill: { color: PRIMARY_DK }, rectRadius: 0.1 });
  T(s, t, { x, y: 2.85, w: 1.75, h: 0.72, fontSize: 14, bold: true, color: TEXT, align: "center", valign: "middle" });
  if (i < 5) T(s, "→", { x: x + 1.75, y: 2.85, w: 0.32, h: 0.72, fontSize: 18, color: PRIMARY, align: "center", valign: "middle" });
});
T(s, "Why it beats existing tools", { x: M, y: 4.05, w: CW, h: 0.35, fontSize: 13, color: MUTED });
[
  ["End-to-end", "No tool-hopping: script, visuals, voice and edit run as one automated pipeline."],
  ["Repeatable at scale", "A job queue turns ANY topic into a video — not one-off generations."],
  ["Platform-ready", "Output is a vertical 9:16 MP4 with captions and voiceover — publish as-is."],
].forEach((c, i) => {
  const x = M + i * 4.11;
  s.addShape(p.shapes.ROUNDED_RECTANGLE, { x, y: 4.5, w: 3.91, h: 2.1, fill: { color: CARD }, rectRadius: 0.12 });
  T(s, c[0], { x: x + 0.25, y: 4.75, w: 3.4, h: 0.4, fontSize: 16, bold: true, color: TEXT });
  T(s, c[1], { x: x + 0.25, y: 5.25, w: 3.4, h: 1.2, fontSize: 12.5, color: MUTED });
});
footer(s, 3);

// ---------- Slide 4 · Architecture + Tech Stack ----------
s = p.addSlide(); s.background = { color: BG };
title(s, "Architecture & Tech Stack");
const arch = [
  ["Topic", "web UI"], ["Script Engine", "NVIDIA GLM"], ["Visual Engine", "FLUX"],
  ["Voice Engine", "edge-tts"], ["Composer", "FFmpeg"], ["Qoneqt Feed", "9:16 MP4"],
];
arch.forEach((b, i) => {
  const x = M + i * 2.07;
  s.addShape(p.shapes.ROUNDED_RECTANGLE, { x, y: 1.35, w: 1.75, h: 1.05, fill: { color: CARD }, rectRadius: 0.1, line: { color: LINE, width: 0.75 } });
  T(s, b[0], { x: x + 0.08, y: 1.47, w: 1.6, h: 0.35, fontSize: 12.5, bold: true, color: TEXT, align: "center" });
  T(s, b[1], { x: x + 0.08, y: 1.86, w: 1.6, h: 0.35, fontSize: 10.5, color: MUTED, align: "center" });
  if (i < 5) T(s, "→", { x: x + 1.75, y: 1.35, w: 0.32, h: 1.05, fontSize: 18, color: PRIMARY, align: "center", valign: "middle" });
});
T(s, "Components", { x: M, y: 2.95, w: 6, h: 0.4, fontSize: 15, bold: true, color: PRIMARY });
s.addText([
  { text: "Frontend — web UI with live job status", options: { bullet: bu(), breakLine: true } },
  { text: "Backend — FastAPI + background worker queue", options: { bullet: bu(), breakLine: true } },
  { text: "AI — NVIDIA GLM (script) · FLUX (visuals) · edge-tts (voice)", options: { bullet: bu(), breakLine: true } },
  { text: "Storage — JSON manifests + MP4 artifacts per stage", options: { bullet: bu() } },
], { x: M, y: 3.4, w: 6.2, h: 2.4, fontSize: 13, color: TEXT, paraSpaceAfter: 8, margin: 0, fontFace: F });
T(s, "Tech Stack", { x: 7.2, y: 2.95, w: 5.5, h: 0.4, fontSize: 15, bold: true, color: PRIMARY });
s.addText([
  { text: "Python · FastAPI · uvicorn", options: { bullet: bu(), breakLine: true } },
  { text: "NVIDIA APIs — GLM + FLUX endpoints", options: { bullet: bu(), breakLine: true } },
  { text: "edge-tts · FFmpeg · Pillow", options: { bullet: bu(), breakLine: true } },
  { text: "Docker · Render (free tier)", options: { bullet: bu() } },
], { x: 7.2, y: 3.4, w: 5.5, h: 2.4, fontSize: 13, color: TEXT, paraSpaceAfter: 8, margin: 0, fontFace: F });
T(s, "Every stage writes a JSON manifest — the next stage consumes measured values, not guesses.",
  { x: M, y: 6.35, w: CW, h: 0.4, fontSize: 12.5, italic: true, color: MUTED });
footer(s, 4);

// ---------- Slide 5 · Key Features ----------
s = p.addSlide(); s.background = { color: BG };
title(s, "Key Features");
[
  ["End-to-end automation", "One prompt in; a finished, captioned, narrated video out — zero manual editing."],
  ["Repeatable at scale", "A job queue renders any topic continuously — the brief's core requirement."],
  ["Duration-fitted voiceover", "Neural TTS re-times itself until the narration fits every scene."],
  ["Reproducible by design", "Deterministic seeds and JSON manifests between every stage."],
  ["Zero-cost shipping", "Built, deployed and running entirely on free tiers."],
].forEach((f, i) => {
  const y = 1.42 + i * 1.06;
  chip(s, M, y, String(i + 1).padStart(2, "0"));
  T(s, f[0], { x: M + 0.85, y: y - 0.02, w: 11, h: 0.4, fontSize: 17, bold: true, color: TEXT });
  T(s, f[1], { x: M + 0.85, y: y + 0.4, w: 11, h: 0.42, fontSize: 13, color: MUTED });
});
footer(s, 5);

// ---------- Slide 6 · Impact + Feasibility ----------
s = p.addSlide(); s.background = { color: BG };
title(s, "Impact & Feasibility");
[
  ["Who benefits", "Creators, community admins, students, small brands — anyone without an editing team."],
  ["Real-world impact", "Idea to publish-ready video in about 3 minutes; consistent daily posting without an editor."],
  ["Scalability", "Queue + worker architecture; every stage is an independent, swappable service."],
].forEach((r, i) => {
  const y = 1.5 + i * 1.55;
  T(s, r[0], { x: M, y, w: 7, h: 0.4, fontSize: 17, bold: true, color: TEXT });
  T(s, r[1], { x: M, y: y + 0.42, w: 7, h: 0.75, fontSize: 13.5, color: MUTED });
  if (i < 2) s.addShape(p.shapes.LINE, { x: M, y: y + 1.32, w: 7, h: 0, line: { color: LINE, width: 0.75 } });
});
s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: 8.2, y: 1.5, w: 4.5, h: 2.15, fill: { color: CARD }, rectRadius: 0.14 });
T(s, "₹0", { x: 8.2, y: 1.75, w: 4.5, h: 1.1, fontSize: 60, bold: true, color: ACCENT, align: "center" });
T(s, "marginal cost per video —\nthe whole stack runs on free tiers", { x: 8.35, y: 2.9, w: 4.2, h: 0.7, fontSize: 12, color: MUTED, align: "center" });
s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: 8.2, y: 3.95, w: 4.5, h: 1.7, fill: { color: CARD }, rectRadius: 0.14 });
T(s, "LIVE", { x: 8.2, y: 4.15, w: 4.5, h: 0.75, fontSize: 36, bold: true, color: PRIMARY, align: "center" });
T(s, "deployed on Render today", { x: 8.35, y: 4.95, w: 4.2, h: 0.5, fontSize: 12, color: MUTED, align: "center" });
T(s, "Feasibility: Docker-reproducible — one image rebuilds the entire service anywhere.",
  { x: M, y: 6.35, w: CW, h: 0.4, fontSize: 12.5, italic: true, color: MUTED });
footer(s, 6);

// ---------- Slide 7 · Demo + Conclusion ----------
s = p.addSlide(); s.background = { color: BG };
title(s, "Demo & Conclusion");
T(s, "Try it live", { x: M, y: 1.25, w: CW, h: 0.35, fontSize: 14, color: MUTED });
s.addText([{ text: "https://ctrl-freak-i4bs.onrender.com", options: { hyperlink: { url: "https://ctrl-freak-i4bs.onrender.com" }, color: PRIMARY } }],
  { x: M, y: 1.6, w: CW, h: 0.55, fontSize: 24, bold: true, fontFace: F, margin: 0 });
T(s, "(free tier — the first request wakes the service in about a minute)", { x: M, y: 2.2, w: CW, h: 0.35, fontSize: 11.5, color: MUTED });
s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: M, y: 2.75, w: CW, h: 2.35, fill: { color: CARD }, rectRadius: 0.14, line: { color: MUTED, width: 1, dashType: "dash" } });
T(s, "[ Add demo screenshots here ]", { x: M, y: 2.75, w: CW, h: 2.35, fontSize: 16, color: MUTED, align: "center", valign: "middle" });
T(s, [
  { text: "Not a concept — ", options: { color: TEXT } },
  { text: "a shipped product: ", options: { color: ACCENT } },
  { text: "any topic in, a publish-ready Qoneqt video out.", options: { color: TEXT } },
], { x: M, y: 5.45, w: CW, h: 0.6, fontSize: 20, bold: true });
T(s, "Why this should be selected: every challenge requirement — pipeline, live deployment, open repo, real distribution on the Qoneqt Global Feed — is already checked.",
  { x: M, y: 6.15, w: CW, h: 0.7, fontSize: 13.5, color: MUTED });
footer(s, 7);

p.writeFile({ fileName: "clipfactory_presentation.pptx" }).then(() => console.log("written: clipfactory_presentation.pptx"));
