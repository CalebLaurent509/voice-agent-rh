# Voice RH - VAPI Orchestration

An automated phone call orchestration system using the VAPI API for candidate qualification and appointment scheduling.

## 📋 Table of Contents

- [Features](#-features)
- [Architecture](#-architecture)
- [Requirements](#-requirements)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Usage](#-usage)
- [File Structure](#-file-structure)
- [Logs and Monitoring](#-logs-and-monitoring)
- [Troubleshooting](#-troubleshooting)

## ✨ Features

- **Automated Calls**: Launch mass phone calls via VAPI
- **Candidate Qualification**: Automatic response analysis and qualification
- **Call Management**: Status tracking and comprehensive logging
- **Email Notifications**: Alerts to recruiters and confirmations to candidates
- **Duplicate Prevention**: Tracking mechanism to avoid re-calling the same numbers
- **Data Persistence**: Storage of summaries and structured data in JSON

## 🏗️ Architecture

```
voice_rh/
├── vapi_orchestration.py      # Main script
├── phone_numbers.csv           # List of numbers to call
├── called_numbers.csv          # Log of completed calls
├── call_summaries.json         # Summaries and structured data
├── .env                        # Environment variables
└── README.md                   # This documentation
```

### Execution Flow

1. **Loading**: Reads numbers from `phone_numbers.csv`
2. **Filtering**: Excludes already-called numbers (from `called_numbers.csv`)
3. **Calling**: Creates a call via VAPI for each number
4. **Tracking**: Waits for the call to transition to "in-progress"
5. **Waiting**: Waits until the call is fully completed
6. **Analysis**: Retrieves summary and structured data
7. **Notification**: Sends emails if the candidate is qualified
8. **Logging**: Records completed calls

## 📦 Requirements

- Python 3.8+
- VAPI account with configured agent and phone
- Gmail account for sending emails (or other SMTP)
- VAPI API keys
- Valid phone numbers

## 🚀 Installation

### 1. Clone or download the project

```bash
cd /home/caleb99/Desktop/EMPTY/voice_rh
```

### 2. Create a virtual environment (recommended)

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

**Contents of `requirements.txt`:**
```
vapi-io==0.1.0
python-dotenv==1.0.0
```

Or manual installation:
```bash
pip install vapi-io python-dotenv
```

## ⚙️ Configuration

### 1. Create the `.env` file

Create a `.env` file at the root of the project with the following variables:

```env
# VAPI Configuration
VAPI_API_KEY=your_vapi_api_key_here
VAPI_AGENT_ID=your_agent_id_here
PHONE_ID=your_phone_id_here

# Email Configuration (Gmail SMTP)
SENDER_EMAIL_SMTP=your_email@gmail.com
SENDER_PASS_SMTP=your_app_password_here
RECRUITER_EMAIL=recruiter@company.com
```

### 2. Gmail Configuration (if applicable)

1. Enable two-factor authentication on your Gmail account
2. Generate an app password:
   - Go to https://myaccount.google.com/apppasswords
   - Select "Mail" and "Windows"
   - Copy the generated password to `SENDER_PASS_SMTP`

### 3. Prepare the `phone_numbers.csv` file

Format with "Number" or "Numéro" header:

```csv
Number
+33612345678
+33687654321
+33698765432
```

Or:

```csv
Numéro
+33612345678
+33687654321
```

## 📱 Usage

### Run the main script

```bash
python vapi_orchestration.py
```

### Example output

```
==> [INFO] [*] 3 numbers to call
==> [INFO] [*] Calling +33612345678 ...
==> [INFO] [*] Waiting for 'in-progress' status...
- Status: ringing
- Status: in-progress
==> [INFO] [*] Call to +33612345678 is now 'in-progress'
- Status: in-progress
- Status: completed
==> [INFO] [*] Call completed (+33612345678) → completed
==> [SUCCESS] [+] Call +33612345678 marked as consumed
==> [INFO] [*] Data saved for +33612345678 → summary + structuredData
```

### Usage modes

**Continuous mode:**
```bash
python vapi_orchestration.py
```

**Test mode (single call):**
Modify the main loop to test with a single number.

**Debug mode:**
Add additional logs or enable VAPI verbose mode.

## 📁 File Structure

### `phone_numbers.csv`
List of numbers to call. Format:
```
Number,FirstName,LastName
+33612345678,John,Doe
+33687654321,Jane,Smith
```

### `called_numbers.csv`
Auto-generated. Logs all calls:
```
Number,Status,Timestamp
+33612345678,completed,2024-01-15 14:23:45
+33687654321,no-answer,2024-01-15 14:35:10
```

### `call_summaries.json`
Summaries and structured data from calls:
```json
[
  {
    "number": "+33612345678",
    "timestamp": "2024-01-15 14:23:45",
    "summary": "Candidate very interested, available next week.",
    "structured_data": {
      "qualified": true,
      "candidate_name": "John Doe",
      "interview_time": "2024-01-22 10:00"
    }
  }
]
```

## 📊 Logs and Monitoring

### Log Levels

- **[INFO]**: General information
- **[SUCCESS]**: Successful operations
- **[WARNING]**: Warnings (incomplete calls, etc.)
- **[ERROR]**: Errors (API errors, exceptions)

### Log Files

- Console: Real-time output
- `called_numbers.csv`: Persistent call history
- `call_summaries.json`: Detailed data

### Recommended Monitoring

Regularly check:
1. Number of successful vs failed calls
2. Email errors
3. Abnormal VAPI statuses

## 🔧 Troubleshooting

### Issue: VAPI authentication failed

**Solution:**
- Verify your `VAPI_API_KEY` in the `.env` file
- Ensure the key is valid in the VAPI dashboard

### Issue: Emails are not being sent

**Solutions:**
- Verify Gmail credentials in `.env`
- Confirm two-factor authentication is enabled
- Use an app password (not your main password)
- Verify the recruiter's email address

### Issue: Calls remain stuck on "ringing"

**Solution:**
- Increase `max_wait` in `wait_for_in_progress()`
- Verify the phone number is valid
- Verify that `PHONE_ID` is correctly configured

### Issue: No structured data returned

**Solution:**
- Verify that your VAPI agent is configured to extract structured data
- Check VAPI analysis logs
- Ensure the bot's prompt requests the necessary information

### Issue: Numbers are not filtered (duplicate calls)

**Solution:**
- Verify that `called_numbers.csv` exists and contains data
- Verify that numbers are exactly identical (format, spaces)
- Delete `called_numbers.csv` to start fresh

## 📝 Important Notes

- **Call Duration**: Calls typically take 5-10 minutes on average
- **Max Wait Time**: 10 minutes per call before timeout
- **Pause Between Calls**: 10 seconds (configurable)
- **Phone Format**: Use international format (+33...)

## 🔐 Security

- NEVER commit the `.env` file
- Use application secrets, not real passwords
- Restrict access to CSV files containing numbers
- Encrypt sensitive data if necessary

## 📈 Future Optimizations

- [ ] Web monitoring interface
- [ ] Parallel calls (instead of sequential)
- [ ] Automatic retry on failure
- [ ] Webhook for real-time notifications
- [ ] Dashboard with statistics
- [ ] PDF report export

## 📞 Support

For any questions or issues:
1. Check detailed logs
2. Verify `.env` configuration
3. Test with VAPI Dashboard
4. Contact VAPI support if necessary

## 📄 License

Property of Starlight PR

---

**Last Updated**: January 2024
