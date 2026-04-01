# LooseBricks — Product Requirements Document

## Product Overview

LooseBricks is a native iOS app for parents and hobbyists to inventory their Lego collections by photographing piles of pieces, then discover what official Lego sets or community MOC designs they can build with what they have.

The core value proposition: you have a pile of mixed-up Lego — LooseBricks tells you what's in it and what you can build.

## Target Users

- Parents managing kids' Lego collections at home
- Hobbyists organising personal collections
- Home-focused, casual users — not resellers or professionals

## MVP Scope (Phase 1)

### Bulk Photo Scanning

- User selects a collection, taps "Scan", takes an overhead photo of pieces spread on a surface
- App provides a guidance overlay: good lighting, spread pieces apart, use a contrasting background
- Photo uploads to backend, ML service processes it, returns identified pieces with confidence scores
- Pieces below a confidence threshold are flagged for manual review
- User confirms, corrects, or removes flagged pieces in a review screen, then saves to collection
- Support for multiple photos per session for large piles

### Inventory & Collections

- Create, rename, and delete collections (e.g. "Kids' box", "Technic bin", "Sorted drawer 3")
- Each collection holds a list of pieces: part number, colour, and quantity
- Merge collections (combine two bins into one)
- Manual add, edit, and remove pieces for when scanning isn't practical
- Search and filter pieces within a collection
- View total piece count and breakdown by category and colour

### Build Suggestions

- Select one or more collections to match against
- Queries Rebrickable's official set and community MOC databases
- Results ranked by completeness (e.g. "You have 97% of Set #10281 — missing 4 pieces")
- Prioritise complete or near-complete builds — no tiny sub-builds
- Filter by: category (Technic, City, Creator, etc.), completeness threshold, piece count range
- Tap a build to see: what you have, what you're missing, link to instructions
- Default minimum completeness threshold of 70%, user-adjustable, to avoid showing builds you barely have pieces for

## Phase 2 (Future)

- Social features: sharing collections, wishlists, family accounts
- Scan accuracy improvements based on user feedback and retraining
- Android version

## Out of Scope

- AI-generated custom build ideas
- Reseller or marketplace features
- Android (until Phase 2)

## Architecture

### Three Layers

**1. iOS App (Swift/SwiftUI)**

- Camera capture pipeline (AVFoundation) optimised for overhead table shots
- Local cache of inventory data for fast browsing
- Piece review and confirmation UI after scanning

**2. Backend API**

- REST API (Python/FastAPI or Node — to be decided during planning)
- User accounts, inventory CRUD, collection management
- Integrates with Rebrickable API to fetch set and MOC part lists
- Build matching engine: compares user inventory against known builds, ranks by completeness percentage
- PostgreSQL database for persistent storage

**3. ML Recognition Service**

- Receives photos from the app via the backend
- Detects and classifies individual Lego pieces (part number + colour) from a bulk photo
- Returns identified pieces with confidence scores
- Deployed as a separate service for independent scaling and model iteration
- Training data: Rebrickable's part catalog images, rendered 3D parts, and user-confirmed corrections over time

### Data Flow — Scan

```
Camera → Backend API → ML Service → piece predictions
                                          ↓
                              Backend returns results
                                          ↓
                            App shows review screen
                                          ↓
                        User confirms → inventory updated
```

## User Accounts & Data

### Authentication

- Sign in with Apple (primary — required by App Store since we offer third-party sign-in)
- Optional email/password as fallback
- No account required to try scanning, but needed to save inventory

### Data Storage

- PostgreSQL for user accounts, collections, and inventory records
- Piece references linked to Rebrickable part IDs for consistency
- Cloud storage (S3 or similar) for scan photos, useful for ML model retraining
- Inventory syncs to backend so data survives device loss or upgrade

### Privacy

- Scan photos stored only with user consent (opt-in for "help improve recognition")
- No sharing of personal data without explicit user action
- GDPR-friendly: account deletion removes all user data

## App Store & Distribution

### Apple Developer Program

- Requires Apple Developer account ($99/year)
- Must comply with Apple App Store Review Guidelines

### App Store Requirements

- Privacy policy: required, must be a publicly accessible URL
- App Privacy "nutrition labels": declare data collected (photos, account info, usage data)
- Sign in with Apple: required since the app offers third-party sign-in
- Age rating: 4+ (no objectionable content)
- App Transport Security: all network calls over HTTPS
- Support iOS 17+ (current and previous major version)
- Support all active iPhone screen sizes
- Camera usage description (NSCameraUsageDescription) explaining why the app needs camera access
- Photo library usage description if allowing import from gallery
- No use of private APIs

### Submission Prep

- TestFlight beta testing before public release
- App Store Connect metadata: description, keywords, category (Utilities or Lifestyle)
- Screenshots for 6.7" and 6.1" display sizes
- App icons at all required resolutions
- Review notes explaining the ML/camera functionality to Apple reviewers
