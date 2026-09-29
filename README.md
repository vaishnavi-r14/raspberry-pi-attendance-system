# AttendVision – Raspberry Pi Smart Attendance System

A smart attendance management system developed using Raspberry Pi, Python, Flask, OpenCV, QR codes, and SQLite.

## 📌 Project Overview

AttendVision is a web-based attendance management system designed to simplify and digitize student attendance.

The system uses a Raspberry Pi and camera module for student identification and provides a web-based dashboard for managing students, attendance records, reports, and administrative activities.

The project combines hardware and software technologies to provide an organized and efficient attendance solution.

## ✨ Features

- 👤 Student registration and management
- 📷 Camera-based face recognition
- 📱 QR-code based student identification
- 📝 Automatic attendance recording
- 📊 Attendance reports
- 🔐 Admin login and authentication
- 📧 OTP-based password reset through email
- 🗃️ SQLite database integration
- 🌐 Web-based dashboard
- 📁 Student photo and QR-code management
- 📋 Component issue and return history
- 🍓 Raspberry Pi GPIO integration

## 🛠️ Technologies Used

### Programming Language

- Python

### Frameworks and Libraries

- Flask
- OpenCV
- NumPy
- QRCode
- Werkzeug
- Python-dotenv

### Frontend

- HTML
- CSS
- JavaScript

### Database

- SQLite

### Hardware

- Raspberry Pi
- Raspberry Pi Camera Module
- GPIO-connected components

### Development Tools

- Git
- GitHub
- VS Code

## 🏗️ Project Structure

```text
raspberry-pi-attendance-system/
│
├── app.py
├── init_db.sql
├── templates/
│   ├── admin.html
│   ├── components_dashboard.html
│   ├── login.html
│   ├── report.html
│   └── student_dashboard.html
│
├── static/
│   ├── icon.png
│   └── manifest.json
│
└── README.md
🔄 How the System Works
The administrator registers and manages student information.
Students can be identified using face recognition or QR codes.
The Raspberry Pi camera captures the required input.
The application identifies the student and records attendance.
Attendance information is stored in the SQLite database.
Administrators can view attendance records and reports through the web dashboard.

📱 Mobile Access
AttendVision can also be accessed from a smartphone through a web browser.
The application is currently provided through a web link and is not published on the Google Play Store.
How to Access
Open the provided application link on a smartphone.
Log in using the appropriate credentials.
Use the available attendance and dashboard features through the mobile browser.
Note: The application currently works through a web browser and does not require installation from the Google Play Store.

⚙️ Installation and Setup
1. Clone the Repository
git clone https://github.com/vaishnavi-r14/raspberry-pi-attendance-system.git
cd raspberry-pi-attendance-system
2. Install Required Python Packages
pip install flask opencv-python numpy qrcode werkzeug python-dotenv
3. Configure Environment Variables
Create a .env file in the project directory and add the required configuration values.
Example:
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-app-password
FLASK_SECRET_KEY=your-secret-key
Do not upload the .env file to GitHub.
4. Initialize the Database
If SQLite is installed, initialize the database using:
sqlite3 attendance.db < init_db.sql
5. Run the Application
python app.py
Then open the application using the local or provided web address.

🍓 Raspberry Pi Setup
The application is designed to run with a Raspberry Pi and camera module.
The Raspberry Pi acts as the hardware platform for camera-based student identification and attendance-related operations.
Required Hardware
Raspberry Pi
Raspberry Pi Camera Module
Required GPIO-connected components
Network connection

🔐 Security
Sensitive credentials are stored using environment variables.
.env files are excluded from the Git repository.
Private student images and face data are not included in the repository.
Authentication is provided for administrative functions.

🎯 Objectives
Reduce manual attendance work.
Provide faster student identification.
Digitize attendance records.
Provide easy access to attendance reports.
Combine Raspberry Pi hardware with web-based software.
Provide convenient access through computers and smartphones.

🚀 Future Enhancements
Cloud database integration
Advanced attendance analytics
Improved mobile interface
Notification system
Public cloud deployment
Role-based access for different users
Enhanced security and authentication

📚 Project Information
Project Name: AttendVision
Project Type: Raspberry Pi and Web-Based Attendance Management System
Platform: Raspberry Pi
Backend: Python Flask
Database: SQLite
Identification: Face Recognition and QR Code
Mobile Access: Web Browser

📄 License
This project is developed for educational and academic purposes.
