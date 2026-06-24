# Project AI Guidelines (AGENTS.md)

This document defines the common rules and guidelines that all AI agents operating on this project must strictly follow.

## 1. Interaction & Communication
- **Communication Language:** Always communicate with the developer (USER) in **Korean** during chat interactions.
- **Guideline Documentation:** This guideline file itself must be maintained and updated in **English**.

## 2. Coding Philosophy & Clean Code
- **Self-Documenting Code (No Redundant Comments):** Avoid writing unnecessary comments in the code. Code should be self-documenting, clean, and clear through self-explanatory naming conventions.
- **No Over-Engineering:** Avoid redundant boilerplate, excessive abstraction, or over-complicated design patterns. Always choose the simplest, most direct, and readable solution (KISS principle).
- **Educational / Learning Context:** This workspace is dedicated to learning and building educational examples. Prioritize code readability and structural clarity over complex, enterprise-level micro-optimizations.

## 3. Runtime & Virtual Environment
- **Shared Virtual Environment:** Do not create separate `.venv` virtual environments in subdirectory or weekly assignment directories.
- **Default Environment Path:** All virtual environment executions, package installations, tests, and command-line processes must always target the project root virtual environment (`file:///Users/jungjin/PycharmProjects/KTB4-jung-AI/.venv`).
