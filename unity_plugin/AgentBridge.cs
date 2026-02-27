/*
 * Unity AI Agent Bridge — Editor Window
 *
 * Drop this file into Assets/Editor/ in your Unity project.
 * Opens a window (Window > AI Agent) that communicates with the
 * Unity AI Agent server via HTTP.
 *
 * Features:
 * - Send tasks to the agent from within the Unity Editor
 * - View task status and results
 * - Quick actions: fix compile errors, review file, generate tests
 * - Auto-detects project path
 */

#if UNITY_EDITOR
using System;
using System.Collections;
using System.Text;
using UnityEditor;
using UnityEngine;
using UnityEngine.Networking;

namespace AIAgent.Editor
{
    public class AgentBridge : EditorWindow
    {
        private string _serverUrl = "http://127.0.0.1:8080";
        private string _taskInput = "";
        private string _statusText = "Not connected";
        private string _lastResult = "";
        private bool _isConnected;
        private bool _isBusy;
        private Vector2 _scrollPos;
        private Vector2 _resultScrollPos;

        [MenuItem("Window/AI Agent")]
        public static void ShowWindow()
        {
            var window = GetWindow<AgentBridge>("AI Agent");
            window.minSize = new Vector2(300, 400);
        }

        private void OnEnable()
        {
            CheckConnection();
        }

        private void OnGUI()
        {
            // Header
            EditorGUILayout.BeginHorizontal(EditorStyles.toolbar);
            GUILayout.Label("Unity AI Agent", EditorStyles.boldLabel);
            GUILayout.FlexibleSpace();

            var statusColor = _isConnected ? Color.green : Color.red;
            var prevColor = GUI.color;
            GUI.color = statusColor;
            GUILayout.Label(_isConnected ? "● Connected" : "● Offline", GUILayout.Width(90));
            GUI.color = prevColor;

            if (GUILayout.Button("Refresh", EditorStyles.toolbarButton, GUILayout.Width(60)))
                CheckConnection();
            EditorGUILayout.EndHorizontal();

            EditorGUILayout.Space(4);

            // Server URL
            EditorGUILayout.BeginHorizontal();
            EditorGUILayout.LabelField("Server", GUILayout.Width(50));
            _serverUrl = EditorGUILayout.TextField(_serverUrl);
            EditorGUILayout.EndHorizontal();

            EditorGUILayout.Space(8);

            // Task input
            EditorGUILayout.LabelField("Task", EditorStyles.boldLabel);
            _taskInput = EditorGUILayout.TextArea(_taskInput, GUILayout.Height(60));

            EditorGUILayout.BeginHorizontal();
            GUI.enabled = _isConnected && !_isBusy && !string.IsNullOrWhiteSpace(_taskInput);
            if (GUILayout.Button("Send Task", GUILayout.Height(28)))
                SendTask(_taskInput);
            GUI.enabled = true;
            EditorGUILayout.EndHorizontal();

            EditorGUILayout.Space(4);

            // Quick actions
            EditorGUILayout.LabelField("Quick Actions", EditorStyles.boldLabel);
            EditorGUILayout.BeginHorizontal();
            GUI.enabled = _isConnected && !_isBusy;

            if (GUILayout.Button("Fix Compile Errors"))
                SendTask("Check for and fix any C# compilation errors in the project.");

            if (GUILayout.Button("Review Selected"))
            {
                var selected = Selection.activeObject;
                if (selected != null)
                {
                    var path = AssetDatabase.GetAssetPath(selected);
                    SendTask($"Review the file {path} for potential issues, bugs, and improvements.");
                }
                else
                {
                    _lastResult = "No file selected in the Project window.";
                }
            }

            if (GUILayout.Button("Generate Tests"))
            {
                var selected = Selection.activeObject;
                if (selected != null)
                {
                    var path = AssetDatabase.GetAssetPath(selected);
                    SendTask($"Generate NUnit tests for {path}.");
                }
                else
                {
                    _lastResult = "No file selected in the Project window.";
                }
            }

            GUI.enabled = true;
            EditorGUILayout.EndHorizontal();

            EditorGUILayout.Space(8);

            // Status
            EditorGUILayout.LabelField("Status", EditorStyles.boldLabel);
            EditorGUILayout.HelpBox(_statusText, _isBusy ? MessageType.Info : MessageType.None);

            // Result
            if (!string.IsNullOrEmpty(_lastResult))
            {
                EditorGUILayout.Space(4);
                EditorGUILayout.LabelField("Last Result", EditorStyles.boldLabel);
                _resultScrollPos = EditorGUILayout.BeginScrollView(
                    _resultScrollPos, GUILayout.MaxHeight(200));
                EditorGUILayout.TextArea(_lastResult, EditorStyles.wordWrappedLabel);
                EditorGUILayout.EndScrollView();
            }
        }

        private void CheckConnection()
        {
            var request = UnityWebRequest.Get($"{_serverUrl}/api/status");
            var op = request.SendWebRequest();
            op.completed += _ =>
            {
                _isConnected = request.result == UnityWebRequest.Result.Success;
                _statusText = _isConnected ? "Connected to agent server" : $"Cannot reach {_serverUrl}";
                Repaint();
                request.Dispose();
            };
        }

        private void SendTask(string task)
        {
            _isBusy = true;
            _statusText = "Sending task...";
            _lastResult = "";

            var projectPath = Application.dataPath.Replace("/Assets", "");
            var body = JsonUtility.ToJson(new TaskPayload
            {
                task = task,
                project = projectPath,
            });

            var request = new UnityWebRequest($"{_serverUrl}/api/tasks", "POST");
            request.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(body));
            request.downloadHandler = new DownloadHandlerBuffer();
            request.SetRequestHeader("Content-Type", "application/json");

            var op = request.SendWebRequest();
            op.completed += _ =>
            {
                _isBusy = false;
                if (request.result == UnityWebRequest.Result.Success)
                {
                    var response = JsonUtility.FromJson<TaskResponse>(
                        request.downloadHandler.text);
                    _statusText = $"Task #{response.task_id} enqueued successfully";
                    _lastResult = $"Task enqueued (ID: {response.task_id}). " +
                                  "Check the dashboard for progress.";
                }
                else
                {
                    _statusText = $"Error: {request.error}";
                    _lastResult = request.downloadHandler?.text ?? request.error;
                }
                Repaint();
                request.Dispose();
            };
        }

        [Serializable]
        private class TaskPayload
        {
            public string task;
            public string project;
        }

        [Serializable]
        private class TaskResponse
        {
            public bool ok;
            public int task_id;
        }
    }
}
#endif
