# 🎬 YT-Vidclipper

[![Live Demo](https://img.shields.io/badge/Live-Demo-brightgreen.svg)](https://yt-vidclipper-fe.vercel.app/)
[![Frontend Repo](https://img.shields.io/badge/Frontend-Repository-blue.svg)](https://github.com/divyanshusoni21/Yt-vidclipper-fe)
[![Backend Repo](https://img.shields.io/badge/Backend-Repository-blue.svg)](https://github.com/divyanshusoni21/Yt-Vidclipper-be)

> **Quickly generate, edit, and download short clips from any YouTube video.**

<img width="2532" height="1284" alt="image" src="https://github.com/user-attachments/assets/6380ee4c-a262-40c5-a9a0-04ee7495bfaa" />


## 🚀 Overview
YT-Vidclipper is a web application that extracts small clips (10s to 5 minutes) from YouTube videos using just the URL. 

Users simply provide a YouTube link, set the start and end times, and click "Get Clips". The backend processes the video and returns a downloadable MP4 file. It also features a built-in video speed editor to speed up or slow down the final clip.

## 💡 The Problem It Solves (Business Case)
I frequently watch long-form YouTube content and want to share insightful moments on platforms like Instagram, Twitter, and WhatsApp. I noticed two problems:
1. Sharing timestamped YouTube links results in very low engagement (people rarely click away from the app they are currently on).
2. Downloading a 2-hour video just to use a desktop app to cut a 30-second clip is a massive, time-consuming hassle.

**The Solution:** YT-Vidclipper automates this workflow, acting as a cloud-based video extraction pipeline that saves users time and local storage space.

## 🛠️ Tech Stack
**Backend & Video Processing (Core Focus)**
*   **Framework:** Django / Django REST Framework
*   **Video Processing:** FFmpeg, yt-dlp
*   **Task Queue :** Django RQ, Redis
*   **Database:** SQLite

**Frontend**
*   **Framework:** React, TailwindCSS
*   **Deployment:** Vercel (Frontend) / Digitalocean (Backend)

## ⚙️ Under the Hood (Backend Architecture)
*Note: As a backend-focused engineer, my primary focus for this project was the data pipeline and video processing logic.*
*   **URL Parsing & Validation:** Securely validates YouTube URLs to prevent malicious inputs.
*   **Stream Extraction:** Connects to the YouTube stream to extract only the requested timeframes without downloading the entire file to the server.
*   **Video Manipulation:** Applies user-defined time range modifications on the server side before serving the final downloadable file.

## 🤖 AI Integration & Development Strategy
To bring this full-stack project to life quickly, I utilized AI to accelerate development:
*   **R&D and Problem Solving:** Used Gemini to brainstorm architectural approaches for handling video streams.
*   **Frontend Generation:** As my core expertise is in Backend Engineering (Python/Django), I leveraged **Antigravity** to write the React frontend based on my API specifications. This allowed me to focus 100% of my time on building a robust, scalable backend and video processing pipeline.
