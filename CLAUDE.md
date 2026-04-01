# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LooseBricks is a native iOS app for parents and hobbyists to inventory Lego collections by photographing piles of pieces, then discover what official sets or community MOC designs they can build with what they have.

## Architecture (Three Layers)

1. **iOS App (Swift/SwiftUI)** — Camera capture via AVFoundation, local inventory cache, piece review UI. Targets iOS 17+, all active iPhone screen sizes.
2. **Backend API** — REST API (Python/FastAPI or Node TBD), user accounts, inventory CRUD, Rebrickable API integration, build matching engine ranked by completeness %. PostgreSQL for storage.
3. **ML Recognition Service** — Separate service receiving photos via backend, detects/classifies Lego pieces (part number + colour) with confidence scores. Independently scalable.

## Key Data Flow

Camera → Backend API → ML Service → piece predictions → Backend returns results → App review screen → User confirms → inventory updated

## External Dependencies

- **Rebrickable API** — part catalog, official set and MOC part lists, part IDs used as canonical references
- **Sign in with Apple** — primary auth (required by App Store guidelines)
- **S3 or similar** — scan photo storage (opt-in for ML retraining)

## Specs

- PRD: `docs/superpowers/specs/2026-04-01-loosebricks-prd.md`
