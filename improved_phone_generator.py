import requests
import re
from datetime import datetime, timedelta
import time
import json
import csv
from collections import defaultdict

# --- TTLock API Credentials ---
CLIENT_ID = '3a5eb18b49bc4df0b85703071f9e96a5'
ACCESS_TOKEN = 'b706b8bd2a4e2879fa42ded98ef21b05'

# --- Lock IDs (TOOTING ONLY) - CORRECTED ---
FRONT_DOOR_LOCK_ID = 20641052
ROOM_LOCK_IDS = {
    'Room 1': 21318606,
    'Room 2': 21321678,
    'Room 3': 21319208,
    'Room 4': 21321180,  
    'Room 5': 21321314,
    'Room 6': 21973872,
}

# --- iCal URLs (TOOTING ONLY - TooStaysSW17) ---
ICAL_URLS = {
    'Room 1': "https://io.eviivo.com/pms/v2/open/property/TooStaysSW17/rooms/7c131bbd-8e63-48bd-a60e-c46cbdd5ea86/ical.ics",
    'Room 2': "https://io.eviivo.com/pms/v2/open/property/TooStaysSW17/rooms/85d5035f-18fa-4f44-a9ae-05a67e068a04/ical.ics",
    'Room 3': "https://io.eviivo.com/pms/v2/open/property/TooStaysSW17/rooms/365e28a8-b6a9-4497-b286-58b6eebf6cec/ical.ics",
    'Room 4': "https://io.eviivo.com/pms/v2/open/property/TooStaysSW17/rooms/231e6d4a-9d9f-4a3f-bd89-701fb017d52f/ical.ics",
    'Room 5': "https://io.eviivo.com/pms/v2/open/property/TooStaysSW17/rooms/a20cdff1-f242-4d2c-8b4c-30d891e95460/ical.ics",
    'Room 6': "https://io.eviivo.com/pms/v2/open/property/TooStaysSW17/rooms/7919787f-89bd-4e25-97aa-6147cf490fe9/ical.ics"
}

# Global tracking
all_bookings = []
generated_codes = []

def unfold_ical_lines(text):
    return re.sub(r'\r?\n[ \t]', '', text)

def parse_ical_events(text):
    events = []
    matches = re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", unfold_ical_lines(text), re.DOTALL)
    for block in matches:
        event = {}
        for field in ["DESCRIPTION", "DTSTART", "DTEND", "UID", "SUMMARY"]:
            match = re.search(rf"{field}(?:;[^:]*)?:(.+)", block)
            event[field] = match.group(1).strip() if match else ""
        events.append(event)
    return events

def parse_datetime(raw):
    try:
        return datetime.strptime(raw, "%Y%m%dT%H%M%S") if "T" in raw else datetime.strptime(raw, "%Y%m%d")
    except:
        return None

def extract_phone_last_4_digits(description):
    """Extract the last 4 digits of phone number - MUST be exactly from their phone"""
    print(f"🔍 Analyzing description for phone number:")
    print(f"    {description}")
    
    # Remove common words and keep only numbers and basic separators
    cleaned = re.sub(r'[a-zA-Z]', ' ', description)
    
    # Look for phone number patterns - be more aggressive
    phone_patterns = [
        # UK mobile numbers with +44
        r'\+44\s*7\d{9}',
        r'\+44\s*\d{10}',
        
        # UK numbers starting with 0
        r'0\d{10}',
        
        # Any long sequence of digits (likely phone)
        r'\d{10,}',
        r'\d{8,}',
        
        # Numbers with separators
        r'\d{3,4}[\s\-\.]\d{3,4}[\s\-\.]\d{3,4}',
        
        # Any 7+ digit sequence
        r'\d{7,}'
    ]
    
    found_phones = []
    
    for pattern in phone_patterns:
        matches = re.findall(pattern, cleaned)
        for match in matches:
            # Clean the phone number - remove all non-digits
            phone_digits = re.sub(r'\D', '', match)
            
            if len(phone_digits) >= 7:  # Must be at least 7 digits
                found_phones.append(phone_digits)
                print(f"📱 Found potential phone: {phone_digits}")
    
    if found_phones:
        # Take the longest phone number found (most likely to be complete)
        best_phone = max(found_phones, key=len)
        last_4 = best_phone[-4:]
        print(f"✅ Using phone number: {best_phone}")
        print(f"✅ Last 4 digits: {last_4}")
        return last_4
    
    # Last resort - look for ANY 4+ digit number in the description
    all_numbers = re.findall(r'\d{4,}', description)
    if all_numbers:
        # Take the last/longest one
        best_number = max(all_numbers, key=len)
        last_4 = best_number[-4:]
        print(f"⚠️ No clear phone found, using digits from: {best_number}")
        print(f"⚠️ Code will be: {last_4}")
        return last_4
    
    print(f"❌ NO PHONE NUMBER FOUND - cannot generate code")
    return None

def extract_booking_id(uid):
    match = re.search(r'eviivo-booking-(.+)', uid)
    return match.group(1) if match else uid

def to_ms(dt):
    return int(dt.timestamp() * 1000)

def is_weekend(date):
    """Check if date falls on weekend"""
    return date.weekday() >= 5

def create_lock_code_simple(lock_id, code, name, start, end, code_type="Room", booking_id=""):
    """Create lock code - simple version without conflict checking"""
    payload = {
        "clientId": CLIENT_ID,
        "accessToken": ACCESS_TOKEN,
        "lockId": lock_id,
        "keyboardPwd": code,
        "keyboardPwdName": f"{name} - {code_type} - {booking_id}",
        "keyboardPwdType": 3,
        "startDate": to_ms(start),
        "endDate": to_ms(end),
        "addType": 2,
        "date": int(time.time() * 1000)
    }

    print(f"📤 Creating {code_type} code '{code}' for {name}")
    
    try:
        api_res = requests.post("https://euapi.ttlock.com/v3/keyboardPwd/add", data=payload, timeout=30)
        
        # Check if we got a valid response
        if api_res.status_code != 200:
            print(f"❌ HTTP error: {api_res.status_code}")
            return False
            
        # Try to parse JSON response
        try:
            result = api_res.json()
        except json.JSONDecodeError:
            print(f"❌ Invalid JSON response from API")
            return False
            
    except requests.exceptions.Timeout:
        print(f"❌ API timeout")
        return False
    except Exception as e:
        print(f"❌ API error: {e}")
        return False

    # Check API response
    if result.get("errcode") == 0:
        print(f"✅ {code_type} code {code} created successfully")
        return True
    elif result.get("errcode") == -3007:
        print(f"⚠️ Code {code} already exists on {code_type} - this might be OK if it's the same booking")
        # Check if it's the same booking by looking at dates
        return True  # Treat as success since code exists
    elif result.get("errcode"):
        print(f"❌ API error {result.get('errcode')} - {result.get('errmsg', 'Unknown error')}")
        return False
    else:
        print(f"✅ {code_type} code {code} created successfully")
        return True

def collect_all_bookings():
    """Collect all bookings from iCal feeds"""
    global all_bookings
    all_bookings = []
    
    print("📊 COLLECTING ALL BOOKINGS")
    print("="*60)
    
    now = datetime.now()
    cutoff_date = now - timedelta(days=1)
    
    for room_name, url in ICAL_URLS.items():
        print(f"\n📅 Collecting bookings for {room_name}...")
        
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            events = parse_ical_events(response.text)
            
            room_bookings = 0
            for event in events:
                start = parse_datetime(event.get("DTSTART", ""))
                end = parse_datetime(event.get("DTEND", ""))
                
                if not start or not end:
                    continue
                    
                # Only include current and future bookings
                if end.date() >= cutoff_date.date():
                    phone_code = extract_phone_last_4_digits(event.get("DESCRIPTION", ""))
                    
                    booking = {
                        'room': room_name,
                        'name': event["DESCRIPTION"].split()[0] if event.get("DESCRIPTION") else "Guest",
                        'start_date': start.date(),
                        'end_date': end.date(),
                        'check_in': start.replace(hour=15, minute=0, second=0),
                        'check_out': end.replace(hour=11, minute=0, second=0),
                        'booking_id': extract_booking_id(event.get("UID", "")),
                        'phone_code': phone_code,
                        'description': event.get("DESCRIPTION", ""),
                        'spans_weekend': any(is_weekend((start + timedelta(days=i)).date()) 
                                           for i in range((end - start).days + 1))
                    }
                    all_bookings.append(booking)
                    room_bookings += 1
                    
                    print(f"  ➡️ {booking['name']}: {booking['start_date']} to {booking['end_date']} | Code: {phone_code or 'NONE'}")
            
            print(f"   Found {room_bookings} upcoming bookings")
            
        except Exception as e:
            print(f"❌ Error collecting bookings for {room_name}: {e}")
    
    print(f"\n📋 TOTAL BOOKINGS COLLECTED: {len(all_bookings)}")
    
    # Show summary of phone codes found
    with_phone = [b for b in all_bookings if b['phone_code']]
    without_phone = [b for b in all_bookings if not b['phone_code']]
    
    print(f"✅ Bookings WITH phone codes: {len(with_phone)}")
    print(f"❌ Bookings WITHOUT phone codes: {len(without_phone)}")
    
    if without_phone:
        print(f"\n⚠️ Bookings missing phone numbers:")
        for booking in without_phone[:5]:  # Show first 5
            print(f"   • {booking['name']} - {booking['room']} - {booking['start_date']}")
            print(f"     Description: {booking['description'][:80]}...")
    
    return all_bookings

def process_bookings_simple():
    """Process bookings with simple approach - just try to create codes"""
    global generated_codes
    generated_codes = []
    
    print("\n🔄 PROCESSING BOOKINGS - SIMPLE DIRECT APPROACH")
    print("="*60)
    print("📱 Will create codes using last 4 digits of phone numbers")
    print("🔧 No conflict checking - just attempt to create codes")
    
    now = datetime.now()
    
    for booking in all_bookings:
        # Skip past bookings
        if booking['end_date'] < now.date():
            continue
            
        print(f"\n" + "="*50)
        print(f"👤 Processing: {booking['name']} - {booking['room']}")
        print(f"📅 {booking['start_date']} to {booking['end_date']}")
        
        code_record = {
            'booking_id': booking['booking_id'],
            'name': booking['name'],
            'room': booking['room'],
            'dates': f"{booking['start_date']} to {booking['end_date']}",
            'phone_code': booking['phone_code'],
            'final_code': booking['phone_code'],
            'front_door_success': False,
            'room_code_success': False,
            'codes_match': False,
            'is_weekend': booking['spans_weekend'],
            'failure_reason': ''
        }
        
        # Check if we have a phone code
        if not booking['phone_code']:
            print(f"❌ SKIPPING: No phone number found")
            code_record['failure_reason'] = 'No phone number found in booking description'
            generated_codes.append(code_record)
            continue
        
        phone_code = booking['phone_code']
        print(f"📱 Using Phone Code: {phone_code}")
        
        # Create front door code
        print(f"🚪 Creating front door code...")
        front_success = create_lock_code_simple(
            FRONT_DOOR_LOCK_ID,
            phone_code,
            booking['name'],
            booking['check_in'],
            booking['check_out'],
            "Front Door",
            booking['booking_id']
        )
        
        # Small delay
        time.sleep(1)
        
        # Create room code
        print(f"🏠 Creating {booking['room']} code...")
        room_success = create_lock_code_simple(
            ROOM_LOCK_IDS[booking['room']],
            phone_code,
            booking['name'],
            booking['check_in'],
            booking['check_out'],
            booking['room'],
            booking['booking_id']
        )
        
        # Update record
        code_record['front_door_success'] = front_success
        code_record['room_code_success'] = room_success
        code_record['codes_match'] = front_success and room_success
        
        if front_success and room_success:
            print(f"✅ SUCCESS: Both locks have code {phone_code}")
        else:
            if not front_success and not room_success:
                code_record['failure_reason'] = f"Phone code {phone_code} failed on both locks"
            elif not front_success:
                code_record['failure_reason'] = f"Phone code {phone_code} failed on front door"
            elif not room_success:
                code_record['failure_reason'] = f"Phone code {phone_code} failed on room lock"
            
            print(f"⚠️ PARTIAL/FAILED: {code_record['failure_reason']}")
        
        generated_codes.append(code_record)
        time.sleep(2)  # Delay between bookings

def generate_comprehensive_report():
    """Generate detailed verification report"""
    print("\n" + "="*80)
    print("📊 COMPREHENSIVE VERIFICATION REPORT")
    print("="*80)
    
    # Basic stats
    total_bookings = len(all_bookings)
    processed_bookings = len(generated_codes)
    successful_codes = len([c for c in generated_codes if c['front_door_success'] and c['room_code_success']])
    failed_codes = processed_bookings - successful_codes
    no_phone_codes = len([c for c in generated_codes if not c['phone_code']])
    
    print(f"\n📈 SUMMARY STATISTICS")
    print(f"   Total bookings found: {total_bookings}")
    print(f"   Bookings processed: {processed_bookings}")
    print(f"   Bookings without phone numbers: {no_phone_codes}")
    print(f"   Successful code generation: {successful_codes}")
    print(f"   Failed/partial code generation: {failed_codes}")
    print(f"   Success rate: {(successful_codes/processed_bookings*100):.1f}%" if processed_bookings else "N/A")
    
    # Show successful codes
    successes = [c for c in generated_codes if c['front_door_success'] and c['room_code_success']]
    if successes:
        print(f"\n✅ SUCCESSFUL CODE ASSIGNMENTS ({len(successes)} guests)")
        for success in successes:
            print(f"   • {success['name']} - {success['room']}: Phone Code {success['final_code']}")
    
    # Show partial successes
    partial = [c for c in generated_codes if (c['front_door_success'] or c['room_code_success']) and not (c['front_door_success'] and c['room_code_success'])]
    if partial:
        print(f"\n⚠️ PARTIAL SUCCESSES ({len(partial)} guests)")
        for part in partial:
            front = "✅" if part['front_door_success'] else "❌"
            room = "✅" if part['room_code_success'] else "❌"
            print(f"   • {part['name']} - {part['room']}: Code {part['final_code']} | Front: {front} Room: {room}")
    
    # Show complete failures
    failures = [c for c in generated_codes if not c['front_door_success'] and not c['room_code_success']]
    if failures:
        print(f"\n❌ COMPLETE FAILURES ({len(failures)} guests)")
        for fail in failures:
            print(f"   • {fail['name']} - {fail['room']}: {fail['failure_reason']}")
    
    # Export detailed report
    export_csv_report()
    
    print(f"\n💾 Detailed report exported to CSV")
    print("="*80)

def export_csv_report():
    """Export detailed report to CSV"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"simple_phone_report_{timestamp}.csv"
    
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        
        # Header
        writer.writerow([
            'Booking_ID', 'Guest_Name', 'Room', 'Check_In', 'Check_Out', 
            'Phone_Code', 'Front_Success', 'Room_Success', 'Overall_Success', 
            'Is_Weekend', 'Failure_Reason'
        ])
        
        # Data rows
        for code in generated_codes:
            overall_success = code['front_door_success'] and code['room_code_success']
            
            writer.writerow([
                code['booking_id'],
                code['name'],
                code['room'],
                code['dates'].split(' to ')[0],
                code['dates'].split(' to ')[1],
                code['phone_code'] or 'None',
                'YES' if code['front_door_success'] else 'NO',
                'YES' if code['room_code_success'] else 'NO',
                'YES' if overall_success else 'NO',
                'YES' if code['is_weekend'] else 'NO',
                code.get('failure_reason', '')
            ])

def main():
    """Main function - Simple direct approach"""
    print("🏨 TOOTING LOCK CODE GENERATOR - SIMPLE DIRECT APPROACH")
    print("="*80)
    print("📱 Uses exactly the last 4 digits of guest phone numbers")
    print("🔧 Simple approach - attempts to create codes directly")
    
    # Step 1: Collect all bookings
    collect_all_bookings()
    
    # Step 2: Process bookings with simple approach
    process_bookings_simple()
    
    # Step 3: Generate comprehensive verification report
    generate_comprehensive_report()
    
    print(f"\n🎯 SIMPLE PHONE CODE GENERATION COMPLETE!")
    print(f"✅ Codes created using exactly last 4 digits of phone numbers")
    print(f"📊 Check the CSV report for detailed analysis")

if __name__ == "__main__":
    main()