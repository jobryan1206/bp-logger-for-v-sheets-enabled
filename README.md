# Blood Pressure Logger — Google Sheets Edition

Streamlit app that logs blood pressure to **Google Sheets** so you can view and edit your data from anywhere.

## Features
- Add systolic, diastolic, pulse, and notes
- Auto-timestamp (or manual date/time)
- Trends chart with 7-day rolling averages, scatter plot, weekly summary
- Google Sheets sync (with local CSV fallback)

## One-time Setup (Google Sheets)
1. **Create a Google Cloud service account**
   - Visit Google Cloud Console → Create Project → “APIs & Services” → “Credentials” → “+ Create Credentials” → **Service account**.
   - In the new service account, go to **Keys** → **Add key** → **Create new key** → **JSON**. Download this file.

2. **Create a target Google Sheet**
   - Make a new Google Sheet (e.g., “Blood Pressure Logger Data”).
   - **Share** the sheet with the service account’s email (ends with `iam.gserviceaccount.com`) and give **Editor** access.
   - Copy the **Sheet URL**.

3. **Add secrets in Streamlit Cloud**
   - In your app’s Streamlit Cloud settings, open **Secrets** and paste something like:
     ```toml
     # .streamlit/secrets.toml (add via Streamlit Cloud's Secrets UI)
     spreadsheet = "https://docs.google.com/spreadsheets/d/XXXXXXXXXXXX/edit"
     worksheet = "bp_data"

     [gcp_service_account]
     type = "service_account"
     project_id = "your-project-id"
     private_key_id = "xxxxxxxxxxxx"
     private_key = "-----BEGIN PRIVATE KEY-----
...your key...
-----END PRIVATE KEY-----
"
     client_email = "your-service-account@your-project.iam.gserviceaccount.com"
     client_id = "1234567890"
     auth_uri = "https://accounts.google.com/o/oauth2/auth"
     token_uri = "https://oauth2.googleapis.com/token"
     auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
     client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/your-service-account%40your-project.iam.gserviceaccount.com"
     ```
   - Tip: If you don’t want to hardcode the spreadsheet, omit `spreadsheet` and the app will **auto-create** one in the service account’s Drive (then you can move/share it later).

## Local Run
```bash
pip install -r requirements.txt
streamlit run app.py
```
- Without secrets, the app falls back to local `bp_data.csv`.

## Deploy to Streamlit Cloud
- Push `app.py`, `requirements.txt`, and this `README.md` to a **public GitHub repo**.
- In Streamlit Cloud: **New app → select repo → app.py → Deploy**.
- Add the **Secrets** (above) in the app’s settings.