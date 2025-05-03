import os
import datetime
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Define required scopes
SCOPES = ['https://www.googleapis.com/auth/calendar.events']

def get_calendar_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    else:
        flow = InstalledAppFlow.from_client_secrets_file(
            'credentials.json', SCOPES
        )

        try:
            # Run local server for OAuth redirect
            creds = flow.run_local_server(port=8080, open_browser=True)
        except Exception as e:
            print("❌ OAuth failed:", e)
            exit(1)

        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return build('calendar', 'v3', credentials=creds)

# Create calendar service
service = get_calendar_service()

# Create event 1 hour from now
now = datetime.datetime.utcnow() + datetime.timedelta(hours=1)
start_time = now.isoformat() + 'Z'
end_time = (now + datetime.timedelta(hours=1)).isoformat() + 'Z'

event = {
    'summary': 'Test Meeting 1',
    'description': 'This is a test meeting created by Google Calendar API',
    'start': {'dateTime': start_time, 'timeZone': 'UTC'},
    'end': {'dateTime': end_time, 'timeZone': 'UTC'},
    'attendees': [{'email': 'sainivedh26@gmail.com'}],
}

# Insert event and send invite
event = service.events().insert(calendarId='primary', body=event, sendUpdates='all').execute()
print(f"\n✅ Event created: {event.get('htmlLink')}")