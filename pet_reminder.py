import streamlit as st
import qrcode
from icalendar import Calendar, Event, Alarm, vDate
from datetime import datetime, timedelta, date, time
import io
import base64
from PIL import Image, ImageDraw, ImageFont
import uuid
import os
import urllib.parse
import hashlib
import boto3
import math
import re
import uuid

# Configure page with mobile optimization
st.set_page_config(
    page_title="Pet Reminder - NexGard SPECTRA",
    page_icon="🐾",
    layout="centered"
)

# AWS Configuration - Use Streamlit secrets for cloud deployment
if "AWS_REGION" in st.secrets:
    # Production: Use Streamlit secrets
    AWS_REGION = st.secrets["AWS_REGION"]
    S3_BUCKET = st.secrets["S3_BUCKET_NAME"]
    aws_access_key_id = st.secrets["AWS_ACCESS_KEY_ID"]
    aws_secret_access_key = st.secrets["AWS_SECRET_ACCESS_KEY"]
    
else:
    # Development: Use environment variables
    AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
    S3_BUCKET = os.getenv('S3_BUCKET_NAME', 'pet-reminder')
    aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')

# Initialize AWS client
try:
    s3_client = boto3.client(
        's3',
        region_name=AWS_REGION,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key
    )
    # Test AWS connection
    s3_client.list_buckets()
    AWS_CONFIGURED = True
except Exception as e:
    AWS_CONFIGURED = False
    st.error(f"⚠️ AWS S3 not configured properly: {str(e)}")
    st.info("Some features may be limited without S3 configuration.")

# Initialize session state for persistence
def init_session_state():
    """Initialize all session state variables"""
    if 'pet_counter' not in st.session_state:
        st.session_state.pet_counter = 1
    
    # Form data persistence
    if 'form_data' not in st.session_state:
        st.session_state.form_data = {}
    
    # Generated content persistence
    if 'generated_content' not in st.session_state:
        st.session_state.generated_content = None
    
    # Generation status
    if 'content_generated' not in st.session_state:
        st.session_state.content_generated = False

def generate_qr_svg(web_page_url):
    """Generate QR code as SVG string for HTML embedding"""
    import qrcode.image.svg
    
    factory = qrcode.image.svg.SvgPathImage
    qr = qrcode.QRCode(
        version=2,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
        image_factory=factory
    )
    
    qr.add_data(web_page_url)
    qr.make(fit=True)
    
    # Generate SVG
    img = qr.make_image()
    svg_string = img.to_string().decode('utf-8')
    
    # Customize SVG colors to match theme
    svg_string = svg_string.replace('fill="black"', 'fill="#000000"')
    svg_string = svg_string.replace('fill="white"', 'fill="#00e47c"')
    
    return svg_string

def save_form_data(pet_name, product_name, start_date, dosage, selected_time, notes):
    """Save current form data to session state"""
    st.session_state.form_data = {
        'pet_name': pet_name,
        'product_name': product_name,
        'start_date': start_date,
        'dosage': dosage,
        'selected_time': selected_time,
        'notes': notes
    }

def get_form_data(key, default=None):
    """Get form data from session state"""
    return st.session_state.form_data.get(key, default)

def format_duration_text(start_date, dosage):
    """Format duration text for display"""
    total_days = dosage * 30
    
    if total_days <= 7:
        return f"{total_days} day{'s' if total_days > 1 else ''}"
    elif total_days <= 31:
        weeks = math.ceil(total_days / 7)
        return f"≈ {weeks} week{'s' if weeks > 1 else ''}"
    elif total_days <= 365:
        months = math.ceil(total_days / 30)
        return f"≈ {months} month{'s' if months > 1 else ''}"
    else:
        years = total_days / 365
        if years >= 2:
            return f"≈ {years:.1f} years"
        else:
            months = math.ceil(total_days / 30)
            return f"≈ {months} months"

def get_fallback_font(size):
    """Get the best available font for the system"""
    font_paths = [
        # Common Windows fonts
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        # Common macOS fonts
        "/System/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        # Common Linux fonts
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/arial.ttf",
        # Streamlit Cloud / Ubuntu fonts
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    ]
    
    for font_path in font_paths:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except:
                continue
    
    # If no fonts found, use default
    return ImageFont.load_default()

def get_next_sequence_number():
    """Get next sequence number from S3 or start from 1"""
    if not AWS_CONFIGURED:
        # Fallback to session state if S3 not available
        if 'pet_counter' not in st.session_state:
            st.session_state.pet_counter = 1
        else:
            st.session_state.pet_counter += 1
        return st.session_state.pet_counter
    
    try:
        # Try to get current counter from S3
        response = s3_client.get_object(Bucket=S3_BUCKET, Key='system/counter.txt')
        current_count = int(response['Body'].read().decode('utf-8'))
    except:
        # If file doesn't exist, start from 1
        current_count = 0
    
    # Increment counter
    next_count = current_count + 1
    
    # Save updated counter back to S3
    try:
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key='system/counter.txt',
            Body=str(next_count).encode('utf-8'),
            ContentType='text/plain'
        )
    except Exception as e:
        st.warning(f"Could not save counter to S3: {e}")
        # Fall back to session state if S3 fails
        if 'pet_counter' not in st.session_state:
            st.session_state.pet_counter = 1
        next_count = st.session_state.pet_counter
        st.session_state.pet_counter += 1
    
    return next_count

def generate_meaningful_id(pet_name, product_name):
    """Generate meaningful ID with sequence number"""
    # Get next sequence number from S3 (persistent)
    current_count = get_next_sequence_number()
    
    # Clean names for URL (remove special characters, spaces)
    clean_pet = ''.join(c for c in pet_name if c.isalnum())[:10]
    clean_product = ''.join(c for c in product_name.split('(')[0] if c.isalnum())[:10]
    
    # Format: QR0001_PetName_ProductName
    meaningful_id = f"QR{current_count:04d}_{clean_pet}_{clean_product}"
    
    return meaningful_id

def create_calendar_reminder(pet_name, product_name, dosage, reminder_time, start_date, notes=""):
    
    # Calculate reminder count for RRULE
    reminder_count = dosage
    
    # Create calendar
    cal = Calendar()
    cal.add('prodid', '-//Pet Medication Reminder//Boehringer Ingelheim//EN')
    cal.add('version', '2.0')
    cal.add('calscale', 'GREGORIAN')
    cal.add('method', 'PUBLISH')

    # Create event
    event = Event()
    event_title = f"{pet_name} - {product_name}"
    
    event.add('summary', event_title)
    if reminder_time == '':
        event.add('description', f"NexGard reminver: {product_name}\nPet: {pet_name}\n{notes}")
    else:
        event.add('description', f"Nexgard reminder: {product_name}\nPet: {pet_name}\nTime: {reminder_time}\n{notes}")
    
    if reminder_time == '':
        event.add('dtstart', vDate(start_date))
        event.add('dtend', vDate(start_date + timedelta(days=1)))
    else:
        start_time = datetime.combine(start_date, datetime.strptime(reminder_time, "%H:%M").time())
        event.add('dtstart', start_time)
        event.add('dtend', start_time + timedelta(hours=1))
    event.add('dtstamp', datetime.now())
    event.add('uid', str(uuid.uuid4()))
    
    # Add recurrence rule with count limit
    rrule = {}
    rrule['freq'] = 'monthly'
    
    if reminder_count > 0:
        rrule['count'] = reminder_count
    
    event.add('rrule', rrule)
    
    alarm = Alarm()
    alarm.add('action', 'DISPLAY')
    alarm.add('description', f'Time to give {product_name} to {pet_name}!')
    alarm.add('trigger', timedelta(minutes=-15))  # 15 minutes before
    event.add_component(alarm)
    
    cal.add_component(event)
    
    return cal.to_ical().decode('utf-8')

def upload_to_s3(calendar_data, file_id):
    """Upload calendar file to S3 and return public URL"""
    if not AWS_CONFIGURED:
        st.warning("⚠️ S3 not configured. Calendar file will be available for download only.")
        return None
        
    try:
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=f"calendars/{file_id}.ics",
            Body=calendar_data.encode('utf-8'),
            ContentType='text/calendar',
            ContentDisposition=f'attachment; filename="{file_id}.ics"'
        )
        
        return f"https://{S3_BUCKET}.s3.{AWS_REGION}.amazonaws.com/calendars/{file_id}.ics"
    except Exception as e:
        st.error(f"Error uploading to S3: {e}")
        return None

def upload_reminder_image_to_s3(image_bytes, file_id):
    """Upload reminder image to S3 and return public URL"""
    if not AWS_CONFIGURED:
        return None
        
    try:
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=f"images/{file_id}_reminder_image.png",
            Body=image_bytes,
            ContentType='image/png',
            ContentDisposition=f'attachment; filename="{file_id}_reminder_image.png"'
        )
        
        return f"https://{S3_BUCKET}.s3.{AWS_REGION}.amazonaws.com/images/{file_id}_reminder_image.png"
    except Exception as e:
        st.error(f"Error uploading image to S3: {e}")
        return None

def create_web_page_html(pet_name, product_name, calendar_url, reminder_details, qr_image_bytes):
    """Create HTML page that serves calendar with device detection"""
    # Base64 encode the web page specific logo
    logo_data_url = ""
    if os.path.exists("Boehringer_Logo_RGB_Black.png"):
        try:
            with open("Boehringer_Logo_RGB_Black.png", "rb") as f:
                logo_bytes = f.read()
                logo_b64 = base64.b64encode(logo_bytes).decode()
                logo_data_url = f"data:image/png;base64,{logo_b64}"
        except:
            pass
    
    # Format reminder times for display
    times_html_list = ""
    if reminder_details['times'] != '':
        times_html_list += f"• {reminder_details['times']}<br>"
        times_html_list = times_html_list.rstrip('<br>')
    
    qr_base64 = base64.b64encode(qr_image_bytes).decode()
    form_url = "https://ah-pet-reminder.streamlit.app"
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🐾 {pet_name.upper()} - Medication Reminder</title>
    
    <!-- Import Google Fonts -->
    <link href="https://fonts.googleapis.com/css2?family=Open+Sans:wght@400;600&display=swap" rel="stylesheet">
    
    <style>
        /* CSS Variables for consistent company styling */
        :root {{
            --primary-font: Arial, sans-serif;
            --secondary-font: 'Open Sans', sans-serif;
            --primary-color: #333333;
            --button-primary-bg: #262C65;
            --button-primary-hover: #0055aa;
            --button-secondary-bg: #6c757d;
            --button-secondary-hover: #545b62;
            --background-color: #ffffff;
            --card-background: #f8f9fa;
            --border-color: #e9ecef;
            --accent-color: #262C65;
        }}
        
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: var(--secondary-font);
            margin: 0;
            padding: 20px;
            background: #ffffff;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--primary-color);
        }}
        
        .container {{
            background: #ffffff;
            border: 2px solid var(--border-color);
            border-radius: 20px;
            padding: 30px;
            max-width: 420px;
            width: 100%;
            text-align: center;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
        }}
        
        .header {{
            margin-bottom: 25px;
        }}
        
        .logo-container {{
            width: 100px;
            height: 100px;
            margin: 0 auto 20px;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        
        .logo-img {{
            max-width: 100px;
            max-height: 100px;
            object-fit: contain;
        }}
        
        .logo-fallback {{
            font-size: 40px;
            color: var(--accent-color);
        }}
        
        /* Company Typography - H1 for pet name */
        .pet-name {{
            font-family: var(--primary-font);
            font-weight: bold;
            font-size: 60px;
            line-height: 67px;
            color: var(--accent-color);
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 2px;
        }}
        
        /* Company Typography - Hero Body for medication */
        .medication {{
            font-family: var(--secondary-font);
            font-weight: 400;
            font-size: 22px;
            line-height: 36px;
            color: var(--primary-color);
            margin-bottom: 25px;
            opacity: 0.9;
        }}
        
        .details {{
            background: var(--card-background);
            border: 1px solid var(--border-color);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 25px;
            text-align: left;
        }}
        
        .detail-row {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 10px;
            font-size: 15px;
        }}
        
        /* Company Typography - Superhead1 for detail labels */
        .detail-label {{
            font-family: var(--secondary-font);
            font-weight: 600;
            font-size: 18px;
            line-height: 28px;
            color: var(--accent-color);
        }}
        
        /* Company Typography - Body1 for detail values */
        .detail-value {{
            font-family: var(--secondary-font);
            font-weight: 400;
            font-size: 18px;
            line-height: 28px;
            color: var(--primary-color);
            flex: 1;
            text-align: right;
        }}
        
        .times-section {{
            background: rgba(38, 44, 101, 0.05);
            border: 1px dashed var(--accent-color);
            border-radius: 10px;
            padding: 15px;
            margin-top: 15px;
            text-align: left;
        }}
        
        /* Company Typography - Superhead1 for times title */
        .times-title {{
            font-family: var(--secondary-font);
            font-weight: 600;
            font-size: 18px;
            line-height: 28px;
            color: var(--accent-color);
            margin-bottom: 8px;
        }}
        
        /* Company Typography - Body2 for times list */
        .times-list {{
            font-family: var(--secondary-font);
            font-weight: 400;
            font-size: 16px;
            line-height: 24px;
            color: var(--primary-color);
        }}
        
        .notes-section {{
            background: rgba(38, 44, 101, 0.05);
            border: 1px dashed var(--accent-color);
            border-radius: 10px;
            padding: 15px;
            margin-top: 15px;
            text-align: left;
        }}
        
        /* Company Typography - Superhead1 for notes title */
        .notes-title {{
            font-family: var(--secondary-font);
            font-weight: 600;
            font-size: 18px;
            line-height: 28px;
            color: var(--accent-color);
            margin-bottom: 8px;
        }}
        
        /* Company Typography - Body2 for notes text */
        .notes-text {{
            font-family: var(--secondary-font);
            font-weight: 400;
            font-size: 16px;
            line-height: 24px;
            color: var(--primary-color);
            opacity: 0.9;
        }}
        
        /* Company Button Styles */
        .btn {{
            display: flex;
            align-items: center;
            justify-content: center;
            width: 100%;
            padding: 0;
            margin: 15px 0;
            border: none;
            border-radius: 12px;
            cursor: pointer;
            text-decoration: none;
            transition: all 0.3s ease;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            box-sizing: border-box;
            padding: 0 40px !important;
        }}
        
        .btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(38, 44, 101, 0.3);
        }}
        
        .btn-primary {{
            font-family: var(--primary-font) !important;
            font-weight: bold !important;
            font-size: 14pt !important;
            text-transform: capitalize !important;
            letter-spacing: 0 !important;
            height: 53px !important;
            border-radius: 6px !important;
            background: var(--accent-color) !important;
            color: #ffffff !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            text-align: center !important;
            line-height: 1 !important;
            padding: 0 40px !important;
        }}

        .btn-primary:hover {{
            background-color: #0055aa !important;
            color: white !important;
            border: 2px solid #0055aa !important;
        }}

        .btn-secondary {{
            font-family: var(--primary-font) !important;
            font-weight: bold !important;
            font-size: 14pt !important;
            text-transform: capitalize !important;
            letter-spacing: 0 !important;
            height: 53px !important;
            border-radius: 6px !important;
            background: var(--accent-color) !important;
            color: #ffffff !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            text-align: center !important;
            line-height: 1 !important;
            background-color: transparent !important;
            color: #262C65 !important;
            border: 2px solid #0055aa !important;   
            padding: 0 40px !important;
        }}
        
        .instructions {{
            background: var(--card-background);
            border-radius: 10px;
            padding: 20px;
            margin-top: 20px;
            color: var(--primary-color);
            line-height: 1.5;
        }}
        
        /* Company Typography - Body2 for instructions title */
        .instructions-title {{
            font-family: var(--secondary-font);
            font-weight: 600;
            font-size: 16px;
            line-height: 24px;
            color: var(--accent-color);
            margin-bottom: 10px;
        }}
        
        .device-specific {{
            margin-top: 15px;
            padding: 15px;
            background: rgba(38, 44, 101, 0.05);
            border-radius: 8px;
            border-left: 4px solid var(--accent-color);
        }}

        /* QR Code section - Desktop Only */
        .qr-section {{
            background-color: var(--card-background);
            padding: 20px;
            text-align: center;
            border: 3px solid var(--accent-color);
            display: block;
        }}
        
        /* Company Typography - Subhead2 for QR title */
        .qr-title {{
            font-family: var(--primary-font);
            font-weight: bold;
            font-size: 22px;
            line-height: 28px;
            color: var(--accent-color);
            margin-bottom: 15px;
        }}

        .qr-image {{
            width: 200px;
            height: 200px;
            margin: 10px auto;
            background-color: #ffffff;
            border: 2px solid var(--accent-color);
            padding: 10px;
            display: block;
        }}

        /* Company Typography - Body2 for QR instructions */
        .qr-instructions {{
            font-family: var(--secondary-font);
            font-weight: 400;
            font-size: 16px;
            line-height: 24px;
            color: var(--primary-color);
            margin: 15px 0 10px 0;
        }}
        
        .qr-link {{
            color: var(--primary-color);
            margin: 10px 0;
        }}
        
        .qr-link a {{
            font-family: var(--primary-font);
            font-weight: bold;
            font-size: 14px;
            text-transform: capitalize;
            letter-spacing: 0;
            color: var(--button-primary-bg);
            text-decoration: underline;
        }}
        
        .scan-tip {{
            background-color: #fff3cd;
            border: 1px solid #ffeaa7;
            padding: 10px;
            margin: 15px 0;
            border-radius: 5px;
            color: #856404;
        }}
        
        /* Company Typography - Disclaimer for scan tip */
        .scan-tip {{
            font-family: var(--secondary-font);
            font-weight: 400;
            font-size: 14px;
            line-height: 24px;
        }}
        
        @media (max-width: 480px) {{
            body {{
                padding: 15px;
            }}
            
            .container {{
                padding: 25px 20px;
            }}
            
            /* Hide QR code section on mobile */
            .qr-section {{
                display: none !important;
            }}
            
            /* Mobile Typography Adjustments */
            .pet-name {{
                font-size: 48px;
                line-height: 53px;
            }}
            
            .medication {{
                font-size: 16px;
                line-height: 28px;
            }}
            
            .detail-label {{
                font-size: 14px;
                line-height: 20px;
            }}
            
            .detail-value {{
                font-size: 14px;
                line-height: 20px;
            }}
            
            .times-title,
            .notes-title {{
                font-size: 14px;
                line-height: 20px;
            }}
            
            .times-list,
            .notes-text {{
                font-size: 10px;
                line-height: 17px;
            }}
            
            .qr-title {{
                font-size: 18px;
                line-height: 24px;
            }}
            
            .qr-instructions {{
                font-size: 10px;
                line-height: 17px;
            }}
            
            .instructions-title {{
                font-size: 10px;
                line-height: 17px;
            }}
            
            .scan-tip {{
                font-size: 11px;
                line-height: 20px;
            }}
            
            .btn {{
                padding: 0 40px !important;
            }}
            
            .logo-container {{
                width: 80px;
                height: 80px;
            }}
            
            .logo-img {{
                max-width: 80px;
                max-height: 80px;
            }}
        }}
        
        /* Media query for tablets and larger screens - Show QR code */
        @media (min-width: 481px) {{
            .qr-section {{
                display: block !important;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo-container">
                {f'<img src="{logo_data_url}" alt="BI Logo" class="logo-img">' if logo_data_url else '<div class="logo-fallback">🐾</div>'}
            </div>
            <div class="pet-name">{pet_name.upper()}</div>
            <div class="medication">({product_name})</div>
        </div>
        
        <div class="details">
            <div class="detail-row">
                <span class="detail-label">Frequency:</span>
                <span class="detail-value">{reminder_details['frequency']}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Start Date:</span>
                <span class="detail-value">{reminder_details['start_date']}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Duration:</span>
                <span class="detail-value">{reminder_details['duration']}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Total Reminders:</span>
                <span class="detail-value">{reminder_details['total_reminders']}</span>
            </div>
            {f"""<div class="times-section">
                <div class="times-title">⏰ Reminder Times:</div>
                <div class="times-list">
                    {times_html_list}
                </div>
            </div>
            """ if times_html_list != "" else ""}
            
            
            {f'''
            <div class="notes-section">
                <div class="notes-title">📝 Additional Notes:</div>
                <div class="notes-text">{reminder_details['notes']}</div>
            </div>
            ''' if reminder_details.get('notes') and reminder_details['notes'].strip() else ''}
        </div>
        
        <a href="{calendar_url}" class="btn btn-primary" download="{pet_name.upper()}_{product_name}_reminder.ics">
            📅 Add to My Calendar
        </a>
        
        <!-- Back to Form Button -->
        <button onclick="window.history.back();" class="btn btn-primary" style="margin-top: 10px;">
            🔙 Back to Form
        </button>

        <!-- Toggle QR Code Button -->
        <button id="toggleQRBtn" onclick="toggleQR()" class="btn btn-secondary" style="margin-top: 10px;">
            📴 Hide QR Code ▲
        </button>

        <!-- QR Code Section (initially hidden with animation) -->
        <div id="qrContainer" style="; overflow: hidden; transition: all 0.5s ease;">
            <div class="qr-title">📱 Scan QR Code to add to Mobile Calendar!</div>
            <div style="text-align: center; margin: 15px 0;">
                <img src="data:image/png;base64,{qr_base64}"
                    alt="QR Code for Pet Reminder"
                    class="qr-image"
                    style="width: 200px; height: 200px; display: block; margin: 0 auto; border: 2px solid #ffffff; padding: 10px; background-color: white;" />
            </div>
        </div>


    <script>
        function toggleQR() {{
            var qrDiv = document.getElementById("qrContainer");
            var btn = document.getElementById("toggleQRBtn");
            if (qrDiv.style.display === "none") {{
                qrDiv.style.display = "block";
                btn.innerHTML = "📴 Hide QR Code ▲";
            }} else {{
                qrDiv.style.display = "none";
                btn.innerHTML = "📱 Show QR Code ▼";
            }}
        }}


        // Device detection and instructions
        function showDeviceInstructions() {{
            const userAgent = navigator.userAgent;
            
            if (/iPhone|iPad|iPod/i.test(userAgent)) {{
                document.querySelector('.ios-instructions').style.display = 'block';
            }} else if (/Android/i.test(userAgent)) {{
                document.querySelector('.android-instructions').style.display = 'block';
            }}
        }}
        
        // Auto-redirect to calendar download on mobile for better UX
        function handleMobileDownload() {{
            const userAgent = navigator.userAgent;
            const downloadBtn = document.querySelector('.btn-primary');
            
            if (/iPhone|iPad|iPod|Android/i.test(userAgent)) {{
                downloadBtn.addEventListener('click', function(e) {{
                    // Let the default download behavior work
                    setTimeout(function() {{
                        // Optional: Show a brief success message
                        downloadBtn.innerHTML = '✅ Calendar File Ready!';
                        downloadBtn.style.background = '#28a745';
                        
                        setTimeout(function() {{
                            downloadBtn.innerHTML = '📅 Add to My Calendar';
                            downloadBtn.style.background = 'var(--accent-color)';
                        }}, 2000);
                    }}, 500);
                }});
            }}
        }}
        
        window.addEventListener('load', function() {{
            showDeviceInstructions();
            handleMobileDownload();
        }});
    </script>
</body>
</html>
"""
    return html_content

def upload_web_page_to_s3(html_content, page_id):
    """Upload HTML page to S3 and return public URL"""
    if not AWS_CONFIGURED:
        return None
        
    try:
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=f"pages/{page_id}.html",
            Body=html_content.encode('utf-8'),
            ContentType='text/html'
        )
        
        return f"https://{S3_BUCKET}.s3.{AWS_REGION}.amazonaws.com/pages/{page_id}.html"
    except Exception as e:
        st.error(f"Error uploading page to S3: {e}")
        return None

def generate_qr_code(web_page_url):
    """Generate QR code that points to the web page"""
    qr = qrcode.QRCode(
        version=2,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=12,
        border=6,
    )
    
    qr.add_data(web_page_url)
    qr.make(fit=True)
    
    # Create QR code with green background
    qr_img = qr.make_image(fill_color="black", back_color="#009FDF")
    
    img_buffer = io.BytesIO()
    qr_img.save(img_buffer, format='PNG')
    img_buffer.seek(0)
    
    return img_buffer.getvalue()

def create_reminder_image(pet_name, product_name, reminder_details, qr_code_bytes):
    """Create a professional business card style reminder image with cloud-compatible fonts"""
    
    # Business card dimensions (landscape orientation for sharing)
    width, height = 1200, 800
    
    # Colors matching your web design
    bg_color = (8, 49, 42)  # #08312a
    accent_color = (0, 228, 124)  # #00e47c
    text_color = (255, 255, 255)  # white
    light_accent = (0, 228, 124, 40)  # Semi-transparent accent
    
    # Create image with high quality
    img = Image.new('RGB', (width, height), bg_color)
    draw = ImageDraw.Draw(img)
    
    # Get fallback fonts with better sizing for cloud deployment
    try:
        large_font = get_fallback_font(48)
        title_font = get_fallback_font(32)
        subtitle_font = get_fallback_font(24)
        detail_font = get_fallback_font(20)
        small_font = get_fallback_font(18)
    except Exception as e:
        # Ultimate fallback - use default font
        base_font = ImageFont.load_default()
        large_font = base_font
        title_font = base_font
        subtitle_font = base_font
        detail_font = base_font
        small_font = base_font
    
    # Draw gradient background effect
    for i in range(height):
        color_factor = i / height
        r = int(8 + (10 - 8) * color_factor)
        g = int(49 + (61 - 49) * color_factor)
        b = int(42 + (51 - 42) * color_factor)
        draw.line([(0, i), (width, i)], fill=(r, g, b))
    
    # Draw decorative border
    border_width = 8
    draw.rectangle([0, 0, width-1, height-1], outline=accent_color, width=border_width)
    
    # Draw BI Logo at top left corner (BIGGER and better handling)
    logo_size = 172  # Increased from 70 to 120
    logo_x = 30
    logo_y = 30
    
    logo_drawn = False
    if os.path.exists("BI-Logo-2.png"):
        try:
            logo_img = Image.open("BI-Logo-2.png")
            # Use thumbnail to maintain aspect ratio properly
            logo_img.thumbnail((logo_size, logo_size), Image.Resampling.LANCZOS)
            actual_w, actual_h = logo_img.size
            
            # Center the logo in the allocated space if it's smaller
            center_x = logo_x + (logo_size - actual_w) // 2
            center_y = logo_y + (logo_size - actual_h) // 2
            
            if logo_img.mode == 'RGBA':
                img.paste(logo_img, (center_x, center_y), logo_img)
            else:
                img.paste(logo_img, (center_x, center_y))
            logo_drawn = True
        except Exception as e:
            print(f"Error loading BI-Logo-2.png: {e}")
            pass
    
    if not logo_drawn and os.path.exists("BI-Logo.png"):
        try:
            logo_img = Image.open("BI-Logo.png")
            logo_img.thumbnail((logo_size, logo_size), Image.Resampling.LANCZOS)
            actual_w, actual_h = logo_img.size
            
            center_x = logo_x + (logo_size - actual_w) // 2
            center_y = logo_y + (logo_size - actual_h) // 2
            
            if logo_img.mode == 'RGBA':
                img.paste(logo_img, (center_x, center_y), logo_img)
            else:
                img.paste(logo_img, (center_x, center_y))
            logo_drawn = True
        except Exception as e:
            print(f"Error loading BI-Logo.png: {e}")
            pass
    
    if not logo_drawn:
        # Fallback: draw simple text instead of emoji
        draw.text((logo_x, logo_y), "BI", fill=accent_color, font=large_font)
    
    # LEFT SIDE: Pet info and details (REDUCED SPACING)
    left_section_width = width // 2 - 50
    left_x = 60
    
    # Pet name (move up to reduce space)
    pet_y = 180  # Reduced from higher value
    draw.text((left_x, pet_y), pet_name.upper(), fill=accent_color, font=large_font)
    
    # Product name (tighter spacing)
    product_y = pet_y + 60  # Reduced spacing
    draw.text((left_x, product_y), '('+product_name+')', fill=text_color, font=title_font)
    
    # Details section (tighter spacing) - REPLACE ICONS WITH TEXT SYMBOLS
    details_y = product_y + 60  # Reduced spacing
    
    # Format frequency better
    frequency_text = reminder_details['frequency']

    details = [
        f" ",
        f"• Frequency: {frequency_text}",
        f"• Starts: {reminder_details['start_date']}",
        f"• Duration: {reminder_details['duration']}",
        f"• Total: {reminder_details['total_reminders']} reminders",
        f" "
    ]
    
    for i, detail in enumerate(details):
        draw.text((left_x, details_y + i * 25), detail, fill=text_color, font=detail_font)
    
    # Times section (tighter spacing) - REPLACE ICON WITH TEXT
    times_y = details_y + len(details) * 25 + 15  # Reduced spacing
    draw.text((left_x, times_y), "Reminder Time:", fill=accent_color, font=detail_font)
    
    times_text = reminder_details['times']
    draw.text((left_x + 20, times_y + 30), f"{times_text}", fill=text_color, font=small_font)
    
    # Notes if present (tighter spacing) - REPLACE ICON WITH TEXT
    if reminder_details.get('notes') and reminder_details['notes'].strip():
        notes_y = times_y + 80  # Adjusted spacing for new layout
        draw.text((left_x, notes_y), "Additional Notes:", fill=accent_color, font=detail_font)
        
        # Wrap notes text
        notes_text = reminder_details['notes']
        max_chars = 40
        if len(notes_text) > max_chars:
            notes_text = notes_text[:max_chars-3] + "..."
        
        draw.text((left_x + 20, notes_y + 30), notes_text, fill=text_color, font=small_font)
    
    # RIGHT SIDE: QR Code section
    qr_section_x = width // 2 + 50
    qr_section_width = width // 2 - 100
    
    # Load and resize QR code
    qr_img = Image.open(io.BytesIO(qr_code_bytes))
    qr_size = 280  # Slightly larger QR code
    qr_img = qr_img.resize((qr_size, qr_size), Image.Resampling.LANCZOS)
    
    # Center QR code in right section
    qr_x = qr_section_x + (qr_section_width - qr_size) // 2
    qr_y = (height - qr_size) // 2 - 20  # Better centering
    
    # Draw QR code background (white rounded rectangle)
    qr_bg_padding = 25
    qr_bg_rect = [qr_x - qr_bg_padding, qr_y - qr_bg_padding, 
                  qr_x + qr_size + qr_bg_padding, qr_y + qr_size + qr_bg_padding]
    draw.rectangle(qr_bg_rect, fill=text_color, outline=accent_color, width=3)
    
    # Add QR code
    img.paste(qr_img, (qr_x, qr_y))
    
    # Instruction text below QR code
    instruction_y = qr_y + qr_size + 35
    #instruction_lines = [
    #    "Scan (or) long press using Mobile",
    #    "to add reminder to your Calendar"
    #]
    
    #for i, line in enumerate(instruction_lines):
    #    # Calculate text width for centering (improved method)
    #    try:
    #        bbox = draw.textbbox((0, 0), line, font=detail_font)
    #        line_width = bbox[2] - bbox[0]
    #    except:
    #        # Fallback calculation
    #        line_width = len(line) * 12
    #    
    #    line_x = qr_section_x + (qr_section_width - line_width) // 2
    #    draw.text((line_x, instruction_y + i * 25), line, fill=text_color, font=detail_font)
    
    # Add decorative elements
    # Top right corner accent
    corner_size = 100
    draw.rectangle([width - corner_size, 0, width, corner_size], fill=accent_color)
    
    # Bottom left corner accent
    draw.rectangle([0, height - corner_size, corner_size, height], fill=accent_color)
    
    return img

def generate_content(pet_name, product_name, start_date, dosage, selected_time, notes):
    """Generate all content and save to session state"""
    try:
        # Calculate reminder count
        duration_text = format_duration_text(start_date, dosage)
        
        calendar_data = create_calendar_reminder(
            pet_name=pet_name,
            product_name=product_name,
            dosage=dosage,
            reminder_time=selected_time,
            start_date=start_date,
            notes=notes
        )
        
        meaningful_id = generate_meaningful_id(pet_name, product_name)
        
        # Create calendar URL (may be None if S3 not configured)
        calendar_url = upload_to_s3(calendar_data, meaningful_id)
        
        reminder_details = {
            'frequency': 'Monthly',
            'start_date': start_date.strftime('%Y-%m-%d'),
            'duration': duration_text,
            'total_reminders': dosage,
            'times': selected_time,
            'notes': notes
        }
        

        # Create web page (may be None if S3 not configured)
        web_page_url = None
        if calendar_url:
            qr_image_bytes_placeholder = generate_qr_code("placeholder")
            html_content = create_web_page_html(pet_name, product_name, calendar_url, reminder_details, qr_image_bytes_placeholder)
            web_page_url = upload_web_page_to_s3(html_content, meaningful_id)
            
            # Generate QR code (use a fallback URL if web page not available)
            qr_target = web_page_url if web_page_url else f"data:text/plain,{pet_name} - {product_name} Reminder"
            qr_image_bytes = generate_qr_code(qr_target)

            html_content = create_web_page_html(pet_name, product_name, calendar_url, reminder_details, qr_image_bytes)
            web_page_url = upload_web_page_to_s3(html_content, meaningful_id)
            
        # Generate the combined reminder image
        reminder_image = create_reminder_image(pet_name, product_name, reminder_details, qr_image_bytes)
        
        # Convert PIL image to bytes for download
        img_buffer = io.BytesIO()
        reminder_image.save(img_buffer, format='PNG', quality=95, dpi=(300, 300))
        reminder_image_bytes = img_buffer.getvalue()
        
        # Upload reminder image to S3 (optional)
        reminder_image_url = upload_reminder_image_to_s3(reminder_image_bytes, meaningful_id)
        
        # Save everything to session state
        st.session_state.generated_content = {
            'meaningful_id': meaningful_id,
            'reminder_image_bytes': reminder_image_bytes,
            'qr_image_bytes': qr_image_bytes,
            'calendar_data': calendar_data,
            'web_page_url': web_page_url,
            'calendar_url': calendar_url,
            'reminder_image_url': reminder_image_url,
            'reminder_details': reminder_details,
            'pet_name': pet_name,
            'product_name': product_name,
            'html_content': html_content
        }
        st.session_state.content_generated = True
        return True
        
    except Exception as e:
        st.error(f"Error generating content: {str(e)}")
        return False

def get_company_styles():
    """
    Returns the complete company style guide CSS for Streamlit with enhanced form label targeting
    """
    return """
    <style>
    /* Import Google Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Open+Sans:wght@400;600&display=swap');
    
    /* CSS Variables for consistent styling */
    :root {
        --primary-font: 'Arial', sans-serif;
        --secondary-font: 'Open Sans', sans-serif;
        --primary-color: #333333;
        --button-primary-bg: #262C65;
        --button-primary-hover: #0056b3;
        --button-secondary-bg: #6c757d;
        --button-secondary-hover: #545b62;
    }
    
    /* Base container styling */
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 100%;
        font-family: var(--secondary-font);
    }
    
    /* Typography Styles - Desktop */
    .company-h1 {
        font-family: var(--primary-font);
        font-weight: bold;
        font-size: 60px;
        line-height: 67px;
        margin: 0;
        color: var(--primary-color);
    }
    
    .company-h2 {
        font-family: var(--primary-font);
        font-weight: bold;
        font-size: 48px;
        line-height: 53px;
        margin: 0;
        color: var(--primary-color);
    }
    
    .company-subhead1 {
        font-family: var(--primary-font);
        font-weight: bold;
        font-size: 28px;
        line-height: 36px;
        margin: 0;
        color: var(--primary-color);
    }
    
    .company-subhead2 {
        font-family: var(--primary-font);
        font-weight: bold;
        font-size: 22px;
        line-height: 28px;
        margin: 0;
        color: var(--primary-color);
    }
    
    .company-superhead1 {
        font-family: var(--secondary-font);
        font-weight: 600;
        font-size: 18px;
        line-height: 28px;
        margin: 0;
        color: var(--primary-color);
    }
    
    .company-hero-body {
        font-family: var(--secondary-font);
        font-weight: 400;
        font-size: 22px;
        line-height: 36px;
        margin: 0;
        color: var(--primary-color);
    }
    
    .company-body1 {
        font-family: var(--secondary-font);
        font-weight: 400;
        font-size: 18px;
        line-height: 28px;
        margin: 0;
        color: var(--primary-color);
    }
    
    .company-body2 {
        font-family: var(--secondary-font);
        font-weight: 400;
        font-size: 16px;
        line-height: 24px;
        margin: 0;
        color: var(--primary-color);
    }
    
    .company-disclaimer {
        font-family: var(--secondary-font);
        font-weight: 400;
        font-size: 14px;
        line-height: 24px;
        margin: 0;
        color: var(--primary-color);
    }
    
    .company-isi {
        font-family: var(--secondary-font);
        font-weight: 400;
        font-size: 18px;
        line-height: 30px;
        margin: 0;
        color: var(--primary-color);
    }
    
    /* Custom Button Styles - Fixed font specifications */
    .company-btn-large {
        font-family: Arial, sans-serif !important;
        font-weight: bold !important;
        font-size: 14pt !important;
        text-transform: capitalize !important;
        letter-spacing: 0 !important;
        height: 53px !important;
        padding: 0 40px !important;
        border-radius: 6px !important;
        border: none !important;
        cursor: pointer !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        text-decoration: none !important;
        transition: background-color 0.3s ease !important;
        padding: 0 40px !important;
    }
    
    .company-btn-medium {
        font-family: Arial, sans-serif !important;
        font-weight: bold !important;
        font-size: 14pt !important;
        text-transform: capitalize !important;
        letter-spacing: 0 !important;
        height: 40px !important;
        padding: 0 40px !important;
        border-radius: 6px !important;
        border: none !important;
        cursor: pointer !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        text-decoration: none !important;
        transition: background-color 0.3s ease !important;
        padding: 0 40px !important;
    }
    
    .company-btn-small {
        font-family: Arial, sans-serif !important;
        font-weight: bold !important;
        font-size: 14pt !important;
        text-transform: capitalize !important;
        letter-spacing: 0 !important;
        height: 33px !important;
        padding: 0 40px !important;
        border-radius: 6px !important;
        border: none !important;
        cursor: pointer !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        text-decoration: none !important;
        transition: background-color 0.3s ease !important;
        padding: 0 40px !important;
    }
    
    .company-btn-primary {
        background-color: #262C65 !important;
        color: white !important;
        padding: 0 40px !important;
    }
    
    .company-btn-primary:hover {
        background-color: #0055aa !important;
        color: white !important;
    }
    
    .company-btn-secondary {
        background-color: transparent !important;
        color: #262C65 !important;
        border: 2px solid #0055aa !important;
        padding: 0 40px !important;
    }
    
    /* Text Links - Fixed font specifications */
    .company-text-link {
        font-family: Arial, sans-serif;
        font-weight: bold;
        font-size: 14px;
        text-transform: capitalize;
        letter-spacing: 0;
        color: var(--button-primary-bg);
        text-decoration: none;
        cursor: pointer;
    }
    
    .company-text-link:hover {
        color: var(--button-primary-hover);
        text-decoration: underline;
    }
    
    .company-text-link-chevron {
        padding-right: 4px;
    }
    
    /* Override Streamlit default button styles - More specific targeting */
    .stButton button,
    .stButton > div > button,
    button[data-testid="stBaseButton-primary"],
    button[data-testid="stBaseButton-secondary"],
    div[data-testid="stButton"] button {
        font-family: Arial, sans-serif !important;
        font-weight: bold !important;
        font-size: 14pt !important;
        text-transform: capitalize !important;
        letter-spacing: 0 !important;
        height: 53px !important;
        padding: 0 40px !important;
        border-radius: 6px !important;
        border: none !important;
        background-color: var(--button-primary-bg) !important;
        color: white !important;
        transition: background-color 0.3s ease !important;
    }
    
    /* Button text content styling */
    .stButton button p,
    .stButton button div,
    .stButton button span,
    button[data-testid="stBaseButton-primary"] p,
    button[data-testid="stBaseButton-primary"] div,
    button[data-testid="stBaseButton-primary"] span,
    div[data-testid="stButton"] button p,
    div[data-testid="stButton"] button div,
    div[data-testid="stButton"] button span {
        font-family: Arial, sans-serif !important;
        font-weight: bold !important;
        font-size: 14pt !important;
        text-transform: capitalize !important;
        letter-spacing: 0 !important;
        color: white !important;
        margin: 0 !important;
    }
    
    .stButton button:hover,
    button[data-testid="stBaseButton-primary"]:hover,
    div[data-testid="stButton"] button:hover {
        background-color: var(--button-primary-hover) !important;
        color: white !important;
    }
    
    .stButton button:hover p,
    .stButton button:hover div,
    .stButton button:hover span,
    button[data-testid="stBaseButton-primary"]:hover p,
    button[data-testid="stBaseButton-primary"]:hover div,
    button[data-testid="stBaseButton-primary"]:hover span {
        color: white !important;
    }
    
    /* COMPREHENSIVE FORM LABEL STYLING - Desktop */
    /* Target the actual Streamlit label structure based on DevTools inspection */
    
    /* Main label targeting - based on your DevTools screenshot */
    div[data-testid="stMarkdownContainer"] p,
    div[data-testid="stMarkdownContainer"] > p,
    .stTimeInput label,
    label[data-testid="stWidgetLabel"] {
        font-family: var(--secondary-font) !important;
        font-weight: 400 !important;
        font-size: 18px !important;
        line-height: 28px !important;
        color: var(--primary-color) !important;
        margin-bottom: 8px !important;
        margin-top: 8px !important;
    }
    
    /* Additional fallback selectors */
    .element-container label,
    .stWidget label,
    .element-container p {
        font-family: var(--secondary-font) !important;
        font-weight: 400 !important;
        font-size: 18px !important;
        line-height: 28px !important;
        color: var(--primary-color) !important;
    }
    
    /* Checkbox alignment and spacing */
    .stCheckbox > label {
        display: flex !important;
        align-items: center !important;
        gap: 12px !important;
        font-family: var(--secondary-font) !important;
        font-weight: 400 !important;
        font-size: 18px !important;
        line-height: 28px !important;
        color: var(--primary-color) !important;
        margin: 0 !important;
        cursor: pointer !important;
    }

    /* Info box styling - full width and proper alignment */
    .stInfo,
    div[data-testid="stAlert"] {
        font-family: var(--secondary-font) !important;
        font-size: 16px !important;
        line-height: 24px !important;
        width: 100% !important;
        margin: 0 !important;
        border-radius: 6px !important;
    }

    .stInfo > div,
    div[data-testid="stAlert"] > div {
        width: 100% !important;
        display: flex !important;
        align-items: center !important;
        min-height: 48px !important;
    }

    .stInfo div[data-testid="stMarkdownContainer"],
    div[data-testid="stAlert"] div[data-testid="stMarkdownContainer"] {
        width: 100% !important;
        margin: 0 !important;
    }

    /* Info box fonts follow company style */
    .stInfo div[data-testid="stMarkdownContainer"] p,
    div[data-testid="stAlert"] div[data-testid="stMarkdownContainer"] p {
        margin: 0 !important;
        font-family: var(--secondary-font) !important;
        font-weight: 400 !important;
        font-size: 16px !important;
        line-height: 24px !important;
        color: var(--primary-color) !important;
    }
    
    /* FONT STYLING FOR INPUT ELEMENTS (keeping fonts, removing visual styling) */
    
    /* Text Input - Font only */
    .stTextInput input {
        font-family: var(--secondary-font) !important;
        font-size: 16px !important;
        line-height: 24px !important;
        color: var(--primary-color) !important;
    }

    /* Text Input Placeholder - Font only */
    .stTextInput input::placeholder {
        font-family: var(--secondary-font) !important;
        font-weight: 400 !important;
        color: #999999 !important;
        font-style: italic !important;
        opacity: 1 !important;
    }

    /* Text Area - Font only */
    .stTextArea textarea {
        font-family: var(--secondary-font) !important;
        font-size: 16px !important;
        line-height: 24px !important;
        color: var(--primary-color) !important;
        resize: vertical !important;
    }

    /* Text Area Placeholder - Font only */
    .stTextArea textarea::placeholder {
        font-family: var(--secondary-font) !important;
        font-weight: 400 !important;
        color: #999999 !important;
        font-style: italic !important;
        opacity: 1 !important;
    }

    /* Date Input - Simplified approach to fix styling */
    .stDateInput input {
        font-family: var(--secondary-font) !important;
        font-size: 16px !important;
        line-height: 24px !important;
        color: var(--primary-color) !important;
    }

    /* Number Input - Font only */
    .stNumberInput input {
        font-family: var(--secondary-font) !important;
        font-size: 16px !important;
        line-height: 24px !important;
        color: var(--primary-color) !important;
    }

    /* Select box - Font only */
    .stSelectbox select {
        font-family: var(--secondary-font) !important;
        font-size: 16px !important;
        line-height: 24px !important;
        color: var(--primary-color) !important;
    }

    /* Time Input - Comprehensive targeting for all possible selectors */
    .stTimeInput select,
    .stTimeInput div select,
    .stTimeInput div[data-baseweb] select,
    .stTimeInput div[data-baseweb="select"] select,
    .stTimeInput div[data-baseweb="select"] div,
    .stTimeInput div[data-testid] select,
    div[data-testid="stTimeInput"] select,
    div[data-testid="stTimeInput"] div select,
    div[data-testid="stTimeInput"] div[data-baseweb] select,
    div[data-testid="stTimeInput"] div[data-baseweb="select"] select,
    div[data-testid="stTimeInput"] div[data-baseweb="select"] div {
        font-family: var(--secondary-font) !important;
        font-size: 16px !important;
        line-height: 24px !important;
        color: var(--primary-color) !important;
    }

    /* Time Input Dropdown Options - All possible option selectors */
    .stTimeInput select option,
    .stTimeInput div select option,
    .stTimeInput div[data-baseweb] select option,
    .stTimeInput div[data-baseweb="select"] select option,
    .stTimeInput div[data-baseweb="select"] div[role="listbox"] div,
    .stTimeInput div[data-baseweb="select"] div[role="option"],
    .stTimeInput div[data-baseweb="select"] div[data-value],
    div[data-testid="stTimeInput"] select option,
    div[data-testid="stTimeInput"] div select option,
    div[data-testid="stTimeInput"] div[data-baseweb] select option,
    div[data-testid="stTimeInput"] div[data-baseweb="select"] select option,
    div[data-testid="stTimeInput"] div[data-baseweb="select"] div[role="listbox"] div,
    div[data-testid="stTimeInput"] div[data-baseweb="select"] div[role="option"],
    div[data-testid="stTimeInput"] div[data-baseweb="select"] div[data-value],
    /* Universal dropdown option selectors */
    div[data-baseweb="select"] div[role="listbox"] div,
    div[data-baseweb="select"] div[role="option"],
    div[data-baseweb="popover"] div[role="listbox"] div,
    div[data-baseweb="popover"] div[role="option"] {
        font-family: var(--secondary-font) !important;
        font-size: 16px !important;
        color: var(--primary-color) !important;
    }
    
    /* Mobile Responsive Styles */
    @media (max-width: 768px) {
        .main .block-container {
            padding-left: 1rem;
            padding-right: 1rem;
        }
        
        /* Mobile input field font size - Font only */
        .stTextInput input, 
        .stSelectbox select, 
        .stTextArea textarea, 
        .stDateInput input, 
        .stNumberInput input,
        .stTimeInput select {
            font-size: 16px !important; /* Prevent zoom on iOS */
        }
        
        /* Mobile Typography */
        .company-h1 {
            font-size: 48px;
            line-height: 53px;
        }
        
        .company-h2 {
            font-size: 42px;
            line-height: 47px;
        }
        
        .company-subhead1 {
            font-size: 22px;
            line-height: 25px;
        }
        
        .company-subhead2 {
            font-size: 18px;
            line-height: 24px;
        }
        
        .company-superhead1 {
            font-size: 14px;
            line-height: 20px;
        }
        
        .company-hero-body {
            font-size: 16px;
            line-height: 28px;
        }
        
        .company-body1 {
            font-size: 14px;
            line-height: 20px;
        }
        
        .company-body2 {
            font-size: 10px;
            line-height: 17px;
        }
        
        .company-disclaimer {
            font-size: 11px;
            line-height: 20px;
        }
        
        .company-isi {
            font-size: 14px;
            line-height: 24px;
        }
        
        /* Mobile button adjustments */
        .stButton button, 
        .company-btn-large, 
        .company-btn-medium, 
        .company-btn-small {
            width: 100% !important;
        }
        
        /* Mobile form label adjustments */
        div[data-testid="stMarkdownContainer"] p,
        div[data-testid="stMarkdownContainer"] > p,
        .stTimeInput label,
        label[data-testid="stWidgetLabel"],
        .element-container label,
        .stWidget label,
        .element-container p {
            font-size: 14px !important;
            line-height: 20px !important;
        }
        
        /* Mobile checkbox adjustments */
        .stCheckbox > label > div:last-child {
            font-size: 14px !important;
            line-height: 20px !important;
        }
        
        /* Mobile info box adjustments */
        .stInfo > div,
        div[data-testid="stAlert"] > div {
            min-height: 40px !important;
        }

        .stInfo div[data-testid="stMarkdownContainer"] p,
        div[data-testid="stAlert"] div[data-testid="stMarkdownContainer"] p {
            font-size: 14pt !important;
            line-height: 20px !important;
        }
    }
    
    /* Hide sidebar completely */
    .css-1d391kg,
    section[data-testid="stSidebar"] {
        display: none !important;
    }
    
    /* Success/Warning/Error messages with company fonts */
    .stSuccess, 
    .stWarning, 
    .stError,
    div[data-testid="stAlert"][data-baseweb="notification"] {
        font-family: var(--secondary-font) !important;
        font-size: 16px !important;
        line-height: 24px !important;
    }
    </style>
    """

def apply_company_styles():
    """Apply the company style guide to the Streamlit app"""
    st.markdown(get_company_styles(), unsafe_allow_html=True)

def company_heading(text, level="h1", custom_class=None):
    """
    Create a company-styled heading
    
    Args:
        text: The heading text
        level: h1, h2, subhead1, subhead2, superhead1, hero-body, body1, body2, disclaimer, isi
        custom_class: Additional CSS classes
    """
    class_name = f"company-{level.replace('_', '-')}"
    if custom_class:
        class_name += f" {custom_class}"
    
    if level in ["h1", "h2"]:
        tag = level
    else:
        tag = "div"
    
    return f'<{tag} class="{class_name}">{text}</{tag}>'

def company_button_html(text, button_type="primary", size="large", onclick=None, custom_class=None):
    """
    Create a company-styled HTML button
    
    Args:
        text: Button text
        button_type: primary or secondary
        size: large, medium, or small
        onclick: JavaScript onclick handler
        custom_class: Additional CSS classes
    """
    classes = f"company-btn-{size} company-btn-{button_type}"
    if custom_class:
        classes += f" {custom_class}"
    
    onclick_attr = f'onclick="{onclick}"' if onclick else ""
    
    return f'<button class="{classes}" {onclick_attr}>{text}</button>'

def company_text_link(text, url=None, has_chevron=False, onclick=None):
    """
    Create a company-styled text link
    
    Args:
        text: Link text
        url: URL for the link
        has_chevron: Whether to add chevron spacing
        onclick: JavaScript onclick handler
    """
    chevron_class = "company-text-link-chevron" if has_chevron else ""
    classes = f"company-text-link {chevron_class}".strip()
    
    if url:
        return f'<a href="{url}" class="{classes}">{text}</a>'
    elif onclick:
        return f'<a class="{classes}" onclick="{onclick}" style="cursor: pointer;">{text}</a>'
    else:
        return f'<span class="{classes}">{text}</span>'

def main():
    # Apply company styles first
    apply_company_styles()
    
    # Initialize session state
    init_session_state()
    
    st.text("")  # Spacing

    # Main form section
    st.markdown(company_heading('📋 Reminder Details', 'subhead2'), unsafe_allow_html=True)
    
    # Pet Name Input - The labels should now be styled automatically
    pet_name = st.text_input(
        "Pet Name", 
        placeholder="e.g., Daisy, Luna, Charlie",
        value=get_form_data('pet_name', ''),
        key="pet_name_input"
    )

    product_name = "NexGard SPECTRA"
    
    # Date Range Selection
    st.markdown(company_heading('📅 Reminder Period', 'body1'), unsafe_allow_html=True)
    col_start, col_end = st.columns(2)
    
    with col_start:
        start_date = st.date_input(
            "Start Date",
            value=get_form_data('start_date', date.today()),
            min_value=date.today(),
            help="First day of reminders",
            key="start_date_input"
        )

    with col_end:
        dosage = st.number_input(
            "Number of Dosages",
            value=get_form_data('dosage', 12),
            min_value=12,
            help="Number of Capsules you have",
            key="number_of_dosage"
        )
    
    # Multiple Times Per Day with Duration Limits
    st.markdown(company_heading('⏰ Reminder Time (Optional)', 'body1'), unsafe_allow_html=True)
    
    # Get saved selected times or use empty list
    saved_times = get_form_data('selected_time', [])
    
    # Option for custom time with validation
    custom_time_data = saved_times[0] if saved_times else None
    custom_checked = custom_time_data is not None

    use_custom_time = st.checkbox("🕐 Custom Time", key="custom", value=custom_checked)

    default_time = datetime.strptime("12:00", "%H:%M").time()

    # Determine the reminder time
    if use_custom_time:
        custom_time = st.time_input("Select custom time", value=default_time, key="custom_time")
        selected_time = custom_time.strftime("%H:%M")
    else:
        selected_time = ''

    notes = st.text_area(
        "Additional Notes (Optional)", 
        placeholder="e.g., Give with food, Check for side effects",
        value=get_form_data('notes', ''),
        key="notes_input"
    )
    
    # Info display using company styling
    if selected_time == '':
        info_text = '📅 Reminder Frequency: **Monthly**'
    else:
        info_text = f'📅 Reminder Frequency: **Monthly** \t\t 🕛 Reminder time: **{selected_time}**'
    
    st.info(info_text)

    # Buttons with company styling
    col1, col2 = st.columns([4, 1])
    
    with col1:
        if st.button("Submit", type="primary", key="submit_btn"):
            if pet_name:
                # Save form data to session state
                save_form_data(pet_name, product_name, start_date, dosage, selected_time, notes)
                
                with st.spinner("Submitting ...."):
                    # Show full-screen spinner overlay
                    st.markdown('''
                    <style>
                    .fullscreen-spinner {
                    position: fixed;
                    top: 0;
                    left: 0;
                    width: 100vw;
                    height: 100vh;
                    background-color: rgba(128, 128, 128, 0.6);
                    z-index: 9999;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    }
                    .spinner-circle {
                    border: 8px solid #f3f3f3;
                    border-top: 8px solid #444;
                    border-radius: 50%;
                    width: 60px;
                    height: 60px;
                    animation: spin 1s linear infinite;
                    }
                    @keyframes spin {
                    0% { transform: rotate(0deg); }
                    100% { transform: rotate(360deg); }
                    }
                    </style>
                    <div class="fullscreen-spinner">
                    <div class="spinner-circle"></div>
                    </div>
                    ''', unsafe_allow_html=True)
                    success = generate_content(pet_name, product_name, start_date, dosage, selected_time, notes)
                    if success:
                        st.success("✅ Calendar reminder generated successfully!  \n🔀 **Redirecting to Validation Page...**")
                        web_page_url = st.session_state.generated_content.get("web_page_url")
                        st.markdown(f"""
                            <meta http-equiv="refresh" content="2;url={web_page_url}">
                                """,  
                                unsafe_allow_html=True)
            else:
                st.warning("⚠️ Please fill in Pet Name")
    
    with col2:
        if st.button("Clear", key="clear_btn"):
            # Clear session state
            st.session_state.form_data = {}
            st.session_state.generated_content = None
            st.session_state.content_generated = False
            st.rerun()

	    
if __name__ == "__main__":
    main()
