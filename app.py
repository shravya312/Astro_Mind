import os
from datetime import date, time, timedelta, datetime
from typing import Optional, Tuple

import streamlit as st
from dotenv import load_dotenv
 
# Optional dependency for Vedic calculations
try:
    import swisseph as swe  # pyswisseph
    _HAS_SWISSEPH = True
except Exception:
    swe = None  # type: ignore
    _HAS_SWISSEPH = False

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


def _parse_utc_offset(offset_text: str) -> Optional[int]:
    """Parse an offset like '+05:30' or '-07' into minutes east of UTC.

    Returns minutes if valid, else None.
    """
    if not offset_text:
        return None
    txt = offset_text.strip()
    sign = 1
    if txt.startswith("+"):
        txt = txt[1:]
    elif txt.startswith("-"):
        sign = -1
        txt = txt[1:]
    if not txt:
        return None
    parts = txt.split(":")
    try:
        hours = int(parts[0])
        minutes = int(parts[1]) if len(parts) > 1 else 0
        if hours < 0 or minutes < 0 or minutes >= 60:
            return None
        total = sign * (hours * 60 + minutes)
        # Clamp to plausible range (-14:00 .. +14:00)
        if total < -14 * 60 or total > 14 * 60:
            return None
        return total
    except Exception:
        return None


RASHI_EN = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]
RASHI_SA = [
    "Mesha", "Vrishabha", "Mithuna", "Karka", "Simha", "Kanya",
    "Tula", "Vrischika", "Dhanu", "Makara", "Kumbha", "Meena",
]
NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni",
    "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
    "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta",
    "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati",
]


def compute_moon_rashi_nakshatra(dt_utc: datetime) -> Optional[Tuple[str, str, int]]:
    """Compute sidereal Moon position using Lahiri ayanamsa and return
    (rashi_label, nakshatra_label, pada) or None if unavailable.
    """
    if not _HAS_SWISSEPH:
        return None
    # Configure sidereal mode
    swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
    # Julian day in UT
    hour_decimal = dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0
    jd_ut = swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, hour_decimal)
    # Tropical ecliptic longitude of Moon
    lon_tropical = swe.calc_ut(jd_ut, swe.MOON)[0][0]
    # Ayanamsa for sidereal conversion
    ayan = swe.get_ayanamsa_ut(jd_ut)
    lon_sidereal = (lon_tropical - ayan) % 360.0

    # Rashi
    rashi_index = int(lon_sidereal // 30.0) % 12
    rashi_label = f"{RASHI_SA[rashi_index]} ({RASHI_EN[rashi_index]})"

    # Nakshatra and Pada
    segment = 360.0 / 27.0  # 13°20'
    nak_index = int(lon_sidereal // segment) % 27
    frac = (lon_sidereal / segment) - nak_index
    pada = int(frac * 4.0) + 1
    if pada < 1:
        pada = 1
    if pada > 4:
        pada = 4
    nak_label = NAKSHATRAS[nak_index]
    return rashi_label, nak_label, pada


def build_reading_prompt(
    name: str,
    place: str,
    bdate: date,
    btime: time,
    system: str,
    vedic_info: Optional[Tuple[str, str, int]],
) -> str:
    base = (
        "You are an experienced astrologer. Create a concise, warm, and empowering personal reading.\n"
        "Constraints: 120-180 words, no bullet points, avoid generic fluff, keep grounded.\n"
        "Include one practical suggestion and end with a single short affirmation starting with 'Affirmation:'.\n"
        f"Name: {name}\nPlace: {place}\nBirth date: {bdate.isoformat()}\nBirth time: {btime.strftime('%H:%M')}\n"
    )
    if system == "Vedic":
        extra = (
            "Use Vedic (Jyotish) astrology with sidereal Lahiri ayanamsa. Focus on the Moon sign (Rāshi) and Nakshatra for core themes.\n"
        )
        if vedic_info:
            rashi_label, nak_label, pada = vedic_info
            extra += f"Computed Moon Rāshi: {rashi_label}. Nakshatra: {nak_label} (Pada {pada}).\n"
    else:
        extra = (
            "Use Western astrology (Sun sign derived from the date) and, if helpful, numerology from the birth date.\n"
        )
    endline = "End with: For guidance and entertainment only.\n"
    return base + extra + endline


def build_qna_prompt(
    question: str,
    name: str,
    place: str,
    bdate: date,
    btime: time,
    reading_text: Optional[str],
    system: str,
    vedic_info: Optional[Tuple[str, str, int]],
) -> str:
    context = reading_text or ""
    if system == "Vedic":
        approach = "Use Vedic (Jyotish) astrology with sidereal Lahiri ayanamsa, leaning on Moon Rāshi and Nakshatra for guidance.\n"
        if vedic_info:
            rashi_label, nak_label, pada = vedic_info
            approach += f"Computed anchors: Moon Rāshi {rashi_label}; Nakshatra {nak_label} (Pada {pada}).\n"
    else:
        approach = "Use Western astrology.\n"
    return (
        "You are an empathetic astrologer-coach. " + approach +
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
    system = st.selectbox("Astrology system", options=["Western", "Vedic"], index=1)
    tz_offset_text = st.text_input(
        "Time zone at birth (UTC offset)", value="+05:30", help="Example: +05:30 for IST, -07:00 for PDT"
    )
    submitted = st.form_submit_button("Generate reading")

if submitted:
    if not name or not place:
        st.error("Please fill in your name and birth place.")
    else:
        # Build UTC datetime from provided local time and offset
        offset_minutes = _parse_utc_offset(tz_offset_text)
        if offset_minutes is None:
            st.error("Invalid UTC offset. Use formats like +05:30 or -07:00.")
            st.stop()

        dt_local = datetime.combine(bdate, btime)
        dt_utc = dt_local - timedelta(minutes=offset_minutes)

        # Vedic Moon Rashi & Nakshatra (pre-compute for prompt if needed)
        vedic = None
        if system == "Vedic" and _HAS_SWISSEPH:
            try:
                vedic = compute_moon_rashi_nakshatra(dt_utc)
            except Exception:
                vedic = None

        # LLM reading (system-aware)
        try:
            prompt = build_reading_prompt(name.strip(), place.strip(), bdate, btime, system, vedic)
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
            "tz_offset": tz_offset_text,
            "vedic": vedic,
            "system": system,
        }
        st.session_state["asked"] = False
        st.session_state["last_q"] = None
        st.session_state["last_a"] = None


reading = st.session_state.get("reading")
if reading:
    st.subheader("Your reading")
    # Show Vedic Moon details if available
    vedic_info = reading.get("vedic")
    if reading.get("system") == "Vedic":
        if vedic_info is None and not _HAS_SWISSEPH:
            st.info("Install 'pyswisseph' to compute Vedic Moon Rāshi and Nakshatra.")
        elif vedic_info:
            rashi_label, nak_label, pada = vedic_info
            st.write(f"Vedic Moon Rāshi: {rashi_label}")
            st.write(f"Nakshatra: {nak_label} (Pada {pada})")

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
                    q.strip(),
                    reading["name"],
                    reading["place"],
                    reading["date"],
                    reading["time"],
                    reading.get("summary"),
                    reading.get("system", "Western"),
                    reading.get("vedic"),
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


