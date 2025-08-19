import os
from datetime import date, time, timedelta
from typing import Optional

import streamlit as st
from dotenv import load_dotenv

st.set_page_config(page_title="AI Astrologer", page_icon="✨", layout="centered")
load_dotenv()


with st.sidebar:
    st.header("LLM settings")
    st.caption("This app uses only Gemini 1.5 Flash for the reading and Q&A.")
    api_key = os.getenv("GEMINI_API_KEY") or st.secrets.get("GEMINI_API_KEY")
    if not api_key:
        st.error("API key missing! Set it in .env or Secrets.")
        st.stop()
    st.success("API key loaded from environment (.env) or Secrets")
    model_name = st.selectbox("Model", options=["gemini-1.5-flash"], index=0)


def gemini_generate_text(api_key: str, model: str, prompt: str) -> str:
    try:
        import google.generativeai as genai
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("google-generativeai is not installed. Run: pip install google-generativeai") from exc

    if not api_key:
        raise RuntimeError("Missing Gemini API Key. Set GEMINI_API_KEY in environment, .env, or Streamlit Secrets.")

    genai.configure(api_key=api_key)
    gmodel = genai.GenerativeModel(model)
    response = gmodel.generate_content(prompt)
    text = getattr(response, "text", None)
    if text:
        return text.strip()
    # Fallback extraction
    try:
        if response.candidates and response.candidates[0].content.parts:
            join_txt = "".join(getattr(p, "text", "") for p in response.candidates[0].content.parts)
            if join_txt:
                return join_txt.strip()
    except Exception:
        pass
    return ""


def build_reading_prompt(name: str, place: str, bdate: date, btime: time) -> str:
    return (
        "You are an experienced astrologer. Create a concise, warm, and empowering personal reading.\n"
        "Constraints: 120-180 words, no bullet points, avoid generic fluff, keep grounded.\n"
        "Use Western astrology (Sun sign derived from the date) and, if helpful, numerology from the birth date.\n"
        "Include one practical suggestion and end with a single short affirmation starting with 'Affirmation:'.\n"
        f"Name: {name}\nPlace: {place}\nBirth date: {bdate.isoformat()}\nBirth time: {btime.strftime('%H:%M')}\n"
        "End with: For guidance and entertainment only.\n"
    )


def build_qna_prompt(question: str, name: str, place: str, bdate: date, btime: time, reading_text: Optional[str]) -> str:
    context = reading_text or ""
    return (
        "You are an empathetic astrologer-coach. Answer the user's question using Western astrology.\n"
        "Constraints: 5-8 sentences, practical and specific, avoid certainty, no medical/financial/legal claims.\n"
        "Offer one actionable next step.\n"
        f"Name: {name}\nPlace: {place}\nBirth date: {bdate.isoformat()}\nBirth time: {btime.strftime('%H:%M')}\n"
        f"Prior reading (if any): {context}\n"
        f"Question: {question}\n"
        "End with: For guidance and entertainment only.\n"
    )

st.title("AI Astrologer ✨")
st.write("Enter your birth details to receive a personalized reading and ask one free question.")

with st.form("birth_form"):
    cols = st.columns(2)
    name = cols[0].text_input("Name", placeholder="Ananya Sarkar")
    place = cols[1].text_input("Birth place", placeholder="Bengaluru, India")
    col2 = st.columns(2)
    bdate = col2[0].date_input("Birth date", value=date(2000, 1, 1))
    btime = col2[1].time_input(
        "Birth time",
        value=time(12, 0),
        step=timedelta(minutes=1),  # allow any minute; you can also type exact time
    )
    submitted = st.form_submit_button("Generate reading")

if submitted:
    if not name or not place:
        st.error("Please fill in your name and birth place.")
    else:
        # LLM-only reading
        try:
            prompt = build_reading_prompt(name.strip(), place.strip(), bdate, btime)
            summary = gemini_generate_text(api_key, model_name, prompt)
        except Exception as exc:
            st.error(f"LLM error: {exc}")
            summary = ""

        st.session_state["reading"] = {
            "name": name.strip(),
            "place": place.strip(),
            "date": bdate,
            "time": btime,
            "summary": summary,
        }
        st.session_state["asked"] = False
        st.session_state["last_q"] = None
        st.session_state["last_a"] = None


reading = st.session_state.get("reading")
if reading:
    st.subheader("Your reading")
    st.write(reading["summary"] or "") 

    st.divider()
    st.subheader("Ask one question")
    disabled = bool(st.session_state.get("asked"))
    q = st.text_area(
        "Your question",
        placeholder="Ask about career, love, health, travel, finance...",
        disabled=disabled,
    )
    ask = st.button("Ask", disabled=disabled)
    if ask:
        if not q.strip():
            st.warning("Please type a question.")
        else:
            try:
                prompt = build_qna_prompt(
                    q.strip(), reading["name"], reading["place"], reading["date"], reading["time"], reading.get("summary")
                )
                ans = gemini_generate_text(api_key, model_name, prompt)
            except Exception as exc:
                st.error(f"LLM error: {exc}")
                ans = ""
            st.session_state["asked"] = True
            st.session_state["last_q"] = q.strip()
            st.session_state["last_a"] = ans
            st.chat_message("user").write(q.strip())
            st.chat_message("assistant").write(ans)
    if (
        st.session_state.get("asked")
        and st.session_state.get("last_q")
        and st.session_state.get("last_a")
        and not ask
    ):
        st.chat_message("user").write(st.session_state["last_q"]) 
        st.chat_message("assistant").write(st.session_state["last_a"]) 

st.caption("For guidance and entertainment purposes only. Not a substitute for professional advice.")


