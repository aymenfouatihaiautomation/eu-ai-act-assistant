"""T8.1 — Interface web de l'assistant AI Act (Gradio).

3 onglets :
  1. Ask                → question (EN/FR/AR) → réponse sourcée + texte exact de la loi
  2. My risk level      → l'arbre de risk.py, sous forme de questionnaire
  3. Deadlines          → le tableau vérifié de dates.py, à une date choisie
(noms courts : avec des noms plus longs, Gradio cache les onglets 2 et 3 derrière « … » sur téléphone)

Ce fichier est À LA RACINE du projet (pas dans src/) : c'est là que Hugging Face
Spaces cherche app.py au moment de la mise en ligne (T8.2).

Lancement, depuis la racine du projet :
    python app.py
puis ouvrir http://127.0.0.1:7860 dans le navigateur.
"""
import os
import re
import sys
from collections import defaultdict
from datetime import date

sys.path.insert(0, "src")  # pour importer answer, risk, dates qui sont dans src/

import gradio as gr

from answer import answer
from dates import DATES, status
from retrieve import warm_up
from risk import explain

# ---------------------------------------------------------------- 1. Question

EXAMPLES = [
    "We use an AI tool to screen job applicants' CVs. Is it high-risk?",
    "Quelles pratiques d'IA sont interdites par l'AI Act ?",
    "متى تنطبق الالتزامات على أنظمة الذكاء الاصطناعي عالية المخاطر؟",
]


# --- Limites (T8.2) : le site est public, chaque question coûte un appel payant à Claude.
#   PER_VISITOR : questions par visiteur (adresse IP) et par jour → empêche un abus
#   PER_DAY     : questions par jour pour TOUT le site            → plafonne la facture
# Réglables sans toucher au code, par les variables d'environnement du serveur.
PER_VISITOR = int(os.getenv("LIMIT_PER_VISITOR", "10"))
PER_DAY = int(os.getenv("LIMIT_PER_DAY", "300"))
_usage = {"day": None, "total": 0, "by_ip": defaultdict(int)}


def visitor_ip(request):
    """Adresse du visiteur. En ligne, le serveur est derrière un relais (proxy) :
    la vraie adresse est la première de l'en-tête x-forwarded-for."""
    if request is None:
        return "local"
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or request.client.host


def allowed(ip):
    """Vrai si ce visiteur peut encore poser une question aujourd'hui (et la compte)."""
    today = date.today()
    if _usage["day"] != today:  # nouveau jour → compteurs à zéro
        _usage.update(day=today, total=0, by_ip=defaultdict(int))
    if _usage["total"] >= PER_DAY or _usage["by_ip"][ip] >= PER_VISITOR:
        return False
    _usage["total"] += 1
    _usage["by_ip"][ip] += 1
    return True


def ask(question, request: gr.Request = None):
    """Appelle answer() et met le résultat en forme pour l'écran.
    (Gradio remplit `request` tout seul : c'est grâce à lui qu'on connaît le visiteur.)"""
    question = (question or "").strip()
    if not question:
        return "Please type a question.", ""
    if len(question) > 1000:
        return "Your question is too long (1000 characters maximum).", ""
    if not allowed(visitor_ip(request)):
        return ("Daily limit reached for this free demo. Please come back tomorrow, "
                "or contact me for a full version."), ""
    try:
        r = answer(question)
    except Exception as e:  # quota, réseau... : jamais de trace Python à l'écran
        print(f"[ask] {type(e).__name__}: {e}")
        return "The service is temporarily unavailable. Please try again in a few minutes.", ""

    text = r["answer"]
    if not r["refused"] and not r.get("format_error"):
        # [S3] → [S3] en gras, pour que l'œil relie la phrase à sa source.
        # Les balises COLLÉES ([S7][S8]) sont mises en gras ENSEMBLE : sinon on obtient
        # **[S7]****[S8]**, que le Markdown n'arrive pas à lire (bug vu le 03/11).
        text = re.sub(r"((?:\[S\d+\])+)", r"**\1**", text)
    text += f"\n\n---\n*{r['disclaimer']}*"

    # « Vérifier » : le texte EXACT de chaque fiche citée — sans IA.
    cited_tags = {f"S{n}" for n in r.get("used", [])}
    blocks = []
    for s in r["sources"]:
        if s["tag"] in cited_tags:
            blocks.append(f"#### [{s['tag']}] {s['label']}\n\n> {s['text']}")
    verify = "\n\n".join(blocks) if blocks else "No source cited."
    return text, verify


# ---------------------------------------------------------------- 2. Haut risque

AREAS_EN = {
    "1": "Biometrics (remote identification, categorisation, emotion recognition)",
    "2": "Critical infrastructure (water, gas, electricity, road traffic, digital)",
    "3": "Education and vocational training (admission, grading, exam proctoring)",
    "4": "Employment and workers management (recruitment, CV screening, promotion, dismissal)",
    "5": "Access to essential services (credit, life/health insurance, public benefits, emergency calls)",
    "6": "Law enforcement",
    "7": "Migration, asylum and border control",
    "8": "Administration of justice and democratic processes (elections)",
}
EXCEPTIONS_EN = {
    "a": "It performs a narrow procedural task",
    "b": "It improves the result of a previously completed human activity",
    "c": "It detects decision-making patterns or deviations, without replacing or influencing the human assessment without proper human review",
    "d": "It performs a preparatory task to an assessment",
}
NONE = "None of these"
YES, NO = "Yes", "No"

VERDICTS = {
    "prohibited": "⛔ **PROHIBITED**",
    "high_risk": "🔴 **HIGH-RISK**",
    "not_high_risk": "🟢 **NOT HIGH-RISK**",
}


def key_of(choice, choices):
    """Retrouve la clé ("4", "a"...) à partir du texte choisi dans la liste."""
    for key, label in choices.items():
        if choice == f"{key}. {label}":
            return key
    return None


def as_choices(d):
    return [f"{k}. {v}" for k, v in d.items()] + [NONE]


def check_risk(prohibited, annex_i, third_party, area, profiling, exception):
    answers = {
        "prohibited": prohibited == YES,
        "annex_i_product": annex_i == YES,
        # 2b n'a de sens que si 2a = oui (le défaut vu dans le terminal, corrigé ici)
        "third_party_assessment": annex_i == YES and third_party == YES,
        "annex_iii_area": key_of(area, AREAS_EN),
        "profiling": profiling == YES,
        "exception": key_of(exception, EXCEPTIONS_EN),
    }
    r = explain(answers)
    basis = r["basis"].replace("Annexe", "Annex")  # risk.py écrit en français ; l'écran est en anglais
    lines = [f"## {VERDICTS[r['verdict']]}", f"**Legal basis:** {basis}"]
    if r["applies"]:
        lines.append(f"**Obligations apply from:** {r['applies']:%d %B %Y}")
    if r["route"] == "art6_3_exception":
        lines.append("⚠ The provider must **document** this assessment before placing the system on the market (Art. 6(4)).")
    if answers["annex_iii_area"]:
        lines.append("⚠ Some Annex III points contain their own exclusions (e.g. point 5: AI used to detect financial fraud). "
                     "Check the exact wording of the point in the **1. Ask** tab.")
    lines.append("ℹ Whatever the verdict, transparency obligations (Art. 50) may apply, e.g. to chatbots or AI-generated content.")
    lines.append("\n*This is an orientation tool, not legal advice.*")
    return "\n\n".join(lines)


# ---------------------------------------------------------------- 3. Dates

def show_dates(day):
    try:
        on = date.fromisoformat((day or "").strip())
    except ValueError:
        return "Please use the format YYYY-MM-DD, for example 2027-01-15."
    applied, pending = status(on)
    rows = ["| Status | From | What |", "|---|---|---|"]
    for e in applied:
        rows.append(f"| ✅ applies | {e['applies']:%d %b %Y} | {e['label']['en']} |")
    for e in pending:
        rows.append(f"| ⏳ not yet | {e['applies']:%d %b %Y} | {e['label']['en']} |")
    return f"### Situation on {on:%d %B %Y}\n\n" + "\n".join(rows) + \
        "\n\n*Each date is checked against the exact text of Articles 111 and 113 (consolidated version after the Digital Omnibus).*"


# ---------------------------------------------------------------- Mise en page

with gr.Blocks(title="EU AI Act Assistant") as demo:
    gr.Markdown("# EU AI Act Assistant\nAnswers cite the exact article. When the text is silent, the assistant says so. "
                "English · Français · العربية")
    # Pour un visiteur qui ne connaît pas l'AI Act : les 4 niveaux de risque + à quoi sert chaque onglet.
    gr.Markdown(
        "**New to the AI Act?** It sorts AI systems into four risk levels: "
        "⛔ **Prohibited** (e.g. social scoring) · 🔴 **High-risk** (e.g. CV screening) · "
        "🔵 **Transparency** (e.g. a chatbot must say it is an AI) · "
        "🟢 **Minimal** (e.g. spam filters, no specific rules).  \n"
        "**1. Ask**: ask a question, get an answer citing the exact article. "
        "**2. My risk level**: answer a few questions to classify your own system. "
        "**3. Deadlines**: see which rules already apply."
    )

    with gr.Tab("1. Ask"):
        question = gr.Textbox(label="Your question (EN / FR / AR)", lines=3, max_length=1000)
        ask_btn = gr.Button("Ask", variant="primary")
        gr.Examples(EXAMPLES, inputs=question)
        answer_md = gr.Markdown()
        with gr.Accordion("🔍 Verify: exact text of the cited sources", open=False):
            verify_md = gr.Markdown()
        ask_btn.click(ask, inputs=question, outputs=[answer_md, verify_md])
        question.submit(ask, inputs=question, outputs=[answer_md, verify_md])

    with gr.Tab("2. My risk level"):
        gr.Markdown("Answer 5 questions to find your risk level (Articles 5 and 6).")
        q1 = gr.Radio([YES, NO], value=NO, label="1. Does the system perform a practice prohibited by Art. 5 (e.g. social scoring, manipulation)?")
        q2a = gr.Radio([YES, NO], value=NO, label="2a. Is it a safety component of a product covered by Annex I (machinery, medical devices, toys...) or that product itself?")
        q2b = gr.Radio([YES, NO], value=NO, visible=False, label="2b. Must that product undergo a third-party conformity assessment?")
        q3 = gr.Radio(as_choices(AREAS_EN), value=NONE, label="3. Is it used in one of these Annex III areas?")
        q4 = gr.Radio([YES, NO], value=NO, visible=False, label="4. Does it perform profiling of natural persons?")
        q5 = gr.Radio(as_choices(EXCEPTIONS_EN), value=NONE, visible=False, label="5. Does one of these exceptions (Art. 6(3)) apply?")
        risk_btn = gr.Button("Check", variant="primary")
        risk_md = gr.Markdown()

        # Questions conditionnelles : on n'affiche que celles qui ont un sens.
        q2a.change(lambda a: gr.update(visible=a == YES), q2a, q2b)
        q3.change(lambda a, p: (gr.update(visible=a != NONE), gr.update(visible=a != NONE and p == NO)),
                  [q3, q4], [q4, q5])
        q4.change(lambda p, a: gr.update(visible=a != NONE and p == NO), [q4, q3], q5)
        risk_btn.click(check_risk, [q1, q2a, q2b, q3, q4, q5], risk_md)

    with gr.Tab("3. Deadlines"):
        gr.Markdown("Every date the AI Act applies, checked against the legal text.")
        day = gr.Textbox(value=date.today().isoformat(), label="Date (YYYY-MM-DD)")
        dates_btn = gr.Button("Show", variant="primary")
        dates_md = gr.Markdown(show_dates(date.today().isoformat()))
        dates_btn.click(show_dates, day, dates_md)
        day.submit(show_dates, day, dates_md)

    # La date du jour est recalculée À CHAQUE visite : sinon, en ligne, elle resterait
    # bloquée au jour où le serveur a démarré.
    demo.load(lambda: (date.today().isoformat(), show_dates(date.today().isoformat())),
              None, [day, dates_md])

if __name__ == "__main__":
    # File d'attente : 2 questions traitées en même temps au maximum, les autres attendent
    # leur tour (au lieu de surcharger le petit serveur gratuit).
    demo.queue(default_concurrency_limit=2)
    print("Chargement du modèle et de l'index...")
    warm_up()
    demo.launch()
