import os
import datetime
import json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Google Calendar API scope
SCOPES = ['https://www.googleapis.com/auth/calendar.events']

# Manual name-to-email mapping (add more as needed)
EMAIL_LOOKUP = {
    "kavinesh": "kavinesh.p123@gmail.com",
    "ashwin": "ashwin.k@example.com"
}

def get_calendar_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    else:
        flow = InstalledAppFlow.from_client_secrets_file(
            'credentials.json', SCOPES)
        creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return build('calendar', 'v3', credentials=creds)

def extract_meeting_info(caption, gemini_client):
    """
    Ask Gemini to extract meeting info in structured JSON
    """
    prompt = f"""Does the following text indicate a meeting or event? If yes, extract the following fields in JSON:
- date (ISO format: YYYY-MM-DD)
- time (e.g., 5:00 PM)
- agenda (brief)
- participants (list of names or emails)

Caption: {caption}

Return a JSON object if meeting info is found. Return "NO" if not related to meetings."""

    contents = [
        {
            "role": "user",
            "parts": [{"text": prompt}]
        }
    ]

    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.0-pro",
            contents=contents
        )
        result = response.text.strip()
        if result.upper() == "NO":
            return None
        return json.loads(result)
    except Exception as e:
        print(f"⚠️ Error parsing meeting info: {e}")
        return None

def schedule_meeting(event_info):
    """
    Create a calendar event using Google Calendar API
    """
    service = get_calendar_service()

    date = event_info['date']
    time_str = event_info['time']
    try:
        start_dt = datetime.datetime.strptime(f"{date} {time_str}", "%Y-%m-%d %I:%M %p")
    except ValueError:
        print("⚠️ Date/time format issue, expected e.g. 2025-05-03 and 5:00 PM")
        return None

    end_dt = start_dt + datetime.timedelta(hours=1)

    # Prepare attendees using email mapping
    attendees = []
    for name in event_info.get('participants', []):
        if "@" in name:
            attendees.append({'email': name})
        else:
            email = EMAIL_LOOKUP.get(name.lower())
            if email:
                attendees.append({'email': email})

    event = {
        'summary': event_info['agenda'],
        'start': {'dateTime': start_dt.isoformat(), 'timeZone': 'Asia/Kolkata'},
        'end': {'dateTime': end_dt.isoformat(), 'timeZone': 'Asia/Kolkata'},
        'attendees': attendees,
        'description': f"Auto-scheduled based on video analysis.\nParticipants: {', '.join(event_info['participants'])}"
    }

    try:
        event = service.events().insert(calendarId='primary', body=event, sendUpdates="all").execute()
        print(f"✅ Meeting scheduled: {event.get('htmlLink')}")
        return event.get('id')
    except Exception as e:
        print(f"❌ Error scheduling meeting: {e}")
        return None

def schedule_if_meeting(caption, gemini_client):
    """
    Full pipeline: Extract → Validate → Schedule if meeting detected
    """
    event_info = extract_meeting_info(caption, gemini_client)
    if event_info:
        print(f"📅 Detected meeting info: {event_info}")
        return schedule_meeting(event_info)
    else:
        print("⛔ No meeting info found in caption.")
        return None