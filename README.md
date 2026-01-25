# UCSF Dental School Appointment Checker

Automated checker for **UCSF Dental School STUDENT (Pre-Doctoral)** appointment availability. Creates GitHub Issues when new slots are detected.

## How It Works

- Uses Playwright browser automation to navigate the UCSF scheduling page at `schedule.ucsfmedicalcenter.org/dentistry/`
- Answers the questionnaire: "Dental exams" → "Over 16" → "Student" (or Faculty)
- Checks the **student clinic** (Pre-Doctoral) appointments by default
- Runs every 60 minutes via GitHub Actions
- Compares against previous check to detect new availability
- Creates a GitHub Issue with slot details when new appointments appear
- Screenshots are saved for debugging

## Setup

### 1. Push to GitHub

```bash
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/ucsf_dentist_school_appointments.git
git push -u origin main
```

### 2. Enable GitHub Actions

- Go to your repo → Settings → Actions → General
- Under "Workflow permissions", select "Read and write permissions"
- Check "Allow GitHub Actions to create and approve pull requests"

### 3. Configure Notifications

To get alerted when new appointments are found:

1. Go to your repo → click "Watch" (top right) → "All Activity"
2. Go to GitHub Settings → Notifications
3. Enable email and/or mobile push notifications for "Issues"

Now you'll get notified immediately when a new student dental appointment opens up!

## Local Testing

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Check STUDENT appointments (default)
python main.py --dry-run

# Check FACULTY appointments instead
python main.py --dry-run --faculty

# Run with visible browser for debugging
python main.py --dry-run --no-headless

# Run with debug logging
python main.py --dry-run --debug
```

## Command Line Options

| Option | Description |
|--------|-------------|
| `--dry-run` | Don't send notifications or update history |
| `--faculty` | Check faculty appointments instead of student |
| `--no-headless` | Show browser window (debugging) |
| `--debug` | Enable debug logging |
| `--api` | Use API method (less reliable) |

## Files

```
├── main.py                 # Entry point
├── config.py               # Configuration constants
├── requirements.txt        # Python dependencies
├── src/
│   ├── browser.py          # Playwright browser automation
│   ├── slot_checker.py     # Slot parsing and comparison
│   └── notifications.py    # GitHub Issues alerts
├── data/
│   ├── slot_history.json   # Historical slot data (auto-updated)
│   └── last_check.png      # Screenshot of last check
└── .github/workflows/
    └── check_appointments.yml  # GitHub Actions workflow
```

## Appointment Types

| Type | Visit Type Name | Description |
|------|-----------------|-------------|
| **Student** (default) | Myc Os Gen Dentistry Pre Doc | Pre-doctoral student clinic - lower cost, longer appointments |
| Faculty | Comprehensive Oral Exam | Faculty practice - more availability, higher cost |

## Customization

### Change Check Frequency

Edit `.github/workflows/check_appointments.yml`:
```yaml
schedule:
  - cron: '0 * * * *'  # Every hour
  # - cron: '*/30 * * * *'  # Every 30 minutes
  # - cron: '0 */2 * * *'  # Every 2 hours
```

### Check Faculty Instead of Student

Edit `.github/workflows/check_appointments.yml`:
```yaml
run: python main.py --faculty
```

## Troubleshooting

### No slots found

This is normal for the student clinic - availability is limited. The checker will notify you when slots open up.

Check `data/last_check.png` to see what the browser saw.

### GitHub Actions failing

1. Check the Actions tab for error logs
2. Ensure workflow permissions are set correctly
3. Check that Playwright can install on Ubuntu

### Notifications not working

1. Ensure you're "Watching" the repository
2. Check GitHub notification settings
3. Verify the `appointment-alert` label exists in your repo
