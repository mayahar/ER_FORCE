# Force – Flight Fatigue & Eye Tracking Research Platform

## Overview

Force is a research-oriented flight simulation platform focused on:

* Fatigue estimation
* Eye tracking integration
* Pilot performance monitoring
* Experimental data collection
* Real-time gameplay interaction

The system combines:

* A flight/game environment
* Research participant management
* Fatigue scoring algorithms
* Eye tracking controller abstraction
* Streamlit UI
* Experiment logging and reporting

---

# Actual Project Structure

```text
core/
├── controller.py
├── database.py
├── database_data.json
├── mock_controller.py
├── research_config.json
├── research_repository.py
└── subject_repository.py

game/

score/
├── fatigue_features.py
└── fatigue_scoring.py

scores_reports/

ui/
├── components.py
├── state.py
├── streamlit_app.py
├── styles.py
└── screens/
    ├── enter_id.py
    ├── game.py
    ├── new_user_sleep_gate.py
    ├── questionnaire.py
    └── results.py

playground.py
.gitignore
```

---

# Architecture

## core/

The `core` package contains the main backend and research-management logic.

### `controller.py`

Main hardware/controller abstraction layer.

Responsibilities likely include:

* Reading real device inputs
* Managing hardware communication
* Providing standardized interfaces to the rest of the system

---

### `mock_controller.py`

Mock implementation used during development.

Known behavior:

* Randomizes unavailable values
* Allows development without physical hardware
* Used as fallback/testing environment

Current development direction:

* Replacing the mock controller with a real implementation
* Preserving the same API/interface
* Returning `None` for unavailable real values

---

### `database.py`

Handles data persistence and database-related operations.

Likely responsibilities:

* Saving participant information
* Loading research/session data
* Managing experiment records

---

### `database_data.json`

Local JSON-based storage/database file.

---

### `research_config.json`

Research configuration file.

Likely stores:

* Experiment settings
* Research parameters
* Thresholds/configuration values
* Gameplay or scoring settings

---

### `research_repository.py`

Research data access layer.

Likely responsibilities:

* Managing research sessions
* Accessing experiment metadata
* Organizing collected results

---

### `subject_repository.py`

Participant/subject management.

Likely responsibilities:

* Creating subjects
* Fetching participant records
* Managing IDs and session linkage

---

# game/

Contains the gameplay/simulation logic.

Known gameplay elements:

* Aircraft starts nose-down
* User must recover quickly
* Balloon/target mechanics exist
* Gameplay difficulty balancing is actively being tuned

Recent balancing considerations:

* Balloon spawn distance
* Balloon movement behavior
* Maintaining achievable reaction windows
* Avoiding overly long flight distances

---

# score/

Contains the fatigue analysis and scoring logic.

## `fatigue_features.py`

Responsible for extracting fatigue-related features.

Potential feature categories:

* Eye movement behavior
* Reaction timing
* Gameplay performance
* Stability metrics
* Attention indicators

---

## `fatigue_scoring.py`

Responsible for calculating the final fatigue score.

Known behavior:

* Features may contribute positively or negatively
* Internal score may become negative
* Final UI display clamps values below 0
* Score normalization/offset logic exists

---

# scores_reports/

Stores generated outputs and reports.

Likely contents:

* Session summaries
* Fatigue score reports
* CSV exports
* Research outputs

---

# ui/

The frontend layer of the system.

The UI is implemented using Streamlit.

## `streamlit_app.py`

Main application entry point.

---

## `state.py`

Application/session state management.

Likely handles:

* Navigation state
* Current participant
* Current experiment state
* Temporary gameplay/session variables

---

## `components.py`

Reusable UI components.

---

## `styles.py`

Centralized styling and visual consistency.

Known requirement:

* All pages should maintain the same design language

---

# UI Screens

## `enter_id.py`

Participant identification screen.

Likely responsibilities:

* Entering participant ID
* Starting or resuming sessions

---

## `new_user_sleep_gate.py`

Sleep-related gating screen.

Likely purpose:

* Preventing invalid participation conditions
* Screening participants based on sleep/fatigue conditions

---

## `questionnaire.py`

Research questionnaire interface.

Likely responsibilities:

* Collecting subjective participant data
* Recording self-reported fatigue/sleep metrics

---

## `game.py`

Main gameplay screen.

Known flow:

* Displays pre-game warning
* Starts simulation/gameplay
* Runs gameplay tasks
* Tracks gameplay metrics

Known UI requirements:

* Warn user that aircraft begins nose-down
* Inform user that eye movements are tracked
* Inform user that audio tasks may occur

---

## `results.py`

Results and scoring display screen.

Likely responsibilities:

* Showing fatigue score
* Displaying performance summaries
* Presenting experiment results

---

# Development Workflow

## Git

The project uses Git with:

* Branching and merges
* Hard resets when needed
* `.gitignore` filtering for runtime/generated files

Ignored content includes:

* Python cache folders
* Runtime/generated session artifacts
* Virtual environments
* Non-essential game assets

---

# Technologies

## Backend

* Python

## Frontend

* Streamlit

## Data Storage

* JSON
* CSV/report outputs

## Research Components

* Eye tracking integration
* Fatigue estimation
* Gameplay telemetry

---

# Current Development Focus

## Active Areas

* Replacing mock controller with real controller
* Integrating eye tracker SDK
* Improving gameplay balancing
* Refining fatigue scoring
* Improving UI consistency
* End-to-end experiment flow stabilization

---

# Experiment Flow

1. Participant enters ID
2. Sleep gate / validation screen appears
3. Questionnaire is completed
4. Gameplay session begins
5. Eye tracking and gameplay data are collected
6. Fatigue features are extracted
7. Fatigue score is calculated
8. Results/report screen is displayed
9. Data is saved into reports/database

---

# Notes

## Important Constraints

* Runtime/generated outputs should not be committed
* Mock and real controllers should share the same interface
* Missing real-device values should return `None`
* UI design should stay visually consistent across screens

---

# Future Documentation Suggestions

Still worth documenting later:

* Installation instructions
* Environment setup
* Hardware setup
* Eye tracker SDK setup
* Experiment protocol
* Scoring methodology
* API/interface contracts
* Testing instructions
* Deployment process

---

# Summary

Force is a Python + Streamlit research platform for fatigue estimation and eye tracking experiments using an interactive flight/game environment.

The project combines:

* Research participant management
* Gameplay interaction
* Fatigue feature extraction
* Scoring algorithms
* Eye tracking integration
* Real-time UI flow
* Experiment data collection

The architecture is organized into clear modules for:

* Core research logic
* Gameplay
* Scoring
* Reporting
* UI screens
* Controller abstraction

making it suitable for both rapid experimentation and future hardware integration.

---

Force is a multidisciplinary flight simulation research platform combining:

* Cognitive neuroscience
* Human factors research
* Eye tracking
* Flight simulation
* Behavioral analytics
* Fatigue estimation
* Real-time interaction systems

The project is focused on creating a robust experimental and training environment for analyzing pilot behavior and spatial disorientation using eye tracking and gameplay-derived metrics.
