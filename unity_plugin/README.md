# Unity AI Agent - Editor Plugin

## Installation

Copy `AgentBridge.cs` to `Assets/Editor/` in your Unity project.

## Usage

1. Start the AI Agent server: `python main.py --web`
2. In Unity Editor: **Window > AI Agent**
3. The plugin auto-connects to `http://127.0.0.1:8080`

## Features

- **Send Task**: Type any task description and send it to the agent
- **Fix Compile Errors**: One-click auto-fix for compilation errors
- **Review Selected**: Select a file in Project window, click to get a code review
- **Generate Tests**: Select a file, auto-generate NUnit tests

## Requirements

- Unity 2021.3+ (uses UnityWebRequest)
- AI Agent server running on localhost:8080
