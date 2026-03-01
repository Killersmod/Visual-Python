{
  "format_version": "1.0.0",
  "file_type": "visualpython_project",
  "graph": {
    "id": "13b8cdf0-d5ce-430a-8456-b85b7d122b6b",
    "metadata": {
      "name": "Untitled Graph",
      "description": "",
      "author": "",
      "version": "1.0.4",
      "created_at": "2026-03-01T21:25:29.488171",
      "modified_at": "2026-03-01T21:59:39.410213",
      "tags": [],
      "flow_entry_points": [
        {
          "node_id": "a55ef4a1-9c36-4498-a282-9e2da444e73f"
        }
      ]
    },
    "nodes": [
      {
        "id": "a55ef4a1-9c36-4498-a282-9e2da444e73f",
        "type": "start",
        "name": "Start",
        "position": {
          "x": -518.0,
          "y": 25.0
        },
        "input_ports": [],
        "output_ports": [
          {
            "name": "exec_out",
            "type": "FLOW",
            "description": "Execution flow output - start of script execution",
            "connections": [
              {
                "source_node_id": "a55ef4a1-9c36-4498-a282-9e2da444e73f",
                "source_port_name": "exec_out",
                "target_node_id": "1fcafc89-59ed-4795-93fa-5681d4abb144",
                "target_port_name": "exec_in"
              },
              {
                "source_node_id": "a55ef4a1-9c36-4498-a282-9e2da444e73f",
                "source_port_name": "exec_out",
                "target_node_id": "4f0e7fc4-0a29-43e5-b962-008c4533fe84",
                "target_port_name": "exec_in"
              }
            ]
          }
        ],
        "properties": {}
      },
      {
        "id": "b4ba01ca-94df-4f32-9f4f-e14bacb66aec",
        "type": "print",
        "name": "Print",
        "position": {
          "x": 600.0,
          "y": -50.0
        },
        "input_ports": [
          {
            "name": "exec_in",
            "type": "FLOW",
            "description": "Execution flow input",
            "required": false,
            "default_value": null,
            "inline_value": null,
            "connection": {
              "source_node_id": "ad97f148-50e8-4dba-82c9-9e8f3955673d",
              "source_port_name": "exec_out",
              "target_node_id": "b4ba01ca-94df-4f32-9f4f-e14bacb66aec",
              "target_port_name": "exec_in"
            }
          },
          {
            "name": "message",
            "type": "ANY",
            "description": "The message to print (overrides configured message)",
            "required": false,
            "default_value": null,
            "inline_value": "World!",
            "connection": null
          },
          {
            "name": "prefix",
            "type": "STRING",
            "description": "Prefix text to prepend to the message",
            "required": false,
            "default_value": null,
            "inline_value": null,
            "connection": null
          },
          {
            "name": "add_timestamp",
            "type": "BOOLEAN",
            "description": "Whether to include a timestamp with the message",
            "required": false,
            "default_value": null,
            "inline_value": null,
            "connection": null
          }
        ],
        "output_ports": [
          {
            "name": "exec_out",
            "type": "FLOW",
            "description": "Execution flow output",
            "connections": []
          },
          {
            "name": "printed_message",
            "type": "STRING",
            "description": "The formatted message that was printed",
            "connections": []
          }
        ],
        "properties": {
          "message": "World!",
          "prefix": "",
          "add_timestamp": false,
          "add_newline": true
        }
      },
      {
        "id": "1fcafc89-59ed-4795-93fa-5681d4abb144",
        "type": "subgraph",
        "name": "Subgraph: 1",
        "position": {
          "x": 208.0,
          "y": 226.0
        },
        "input_ports": [
          {
            "name": "exec_in",
            "type": "FLOW",
            "description": "Execution flow input - triggers subgraph execution",
            "required": false,
            "default_value": null,
            "inline_value": null,
            "connection": {
              "source_node_id": "a55ef4a1-9c36-4498-a282-9e2da444e73f",
              "source_port_name": "exec_out",
              "target_node_id": "1fcafc89-59ed-4795-93fa-5681d4abb144",
              "target_port_name": "exec_in"
            }
          }
        ],
        "output_ports": [
          {
            "name": "exec_out",
            "type": "FLOW",
            "description": "Execution flow output - continues after subgraph completes",
            "connections": []
          }
        ],
        "properties": {
          "subgraph_id": "380479c0-9622-4c2a-9563-0a488dbcf3e5",
          "subgraph_name": "1",
          "input_mappings": {},
          "output_mappings": {},
          "dynamic_inputs": [],
          "dynamic_outputs": [],
          "is_reference_based": true,
          "subgraph_path": "C:\\Users\\DylanSmart\\VisualPython\\Workflows\\1.vpy",
          "reference_version": "1.0.2"
        }
      },
      {
        "id": "c9424ec9-b93f-4b9a-872f-19a46d941dba",
        "type": "get_case_variable",
        "name": "Get Case Variable",
        "position": {
          "x": -197.5475,
          "y": -30.74249999999998
        },
        "input_ports": [
          {
            "name": "exec_in",
            "type": "FLOW",
            "description": "Execution flow input",
            "required": false,
            "default_value": null,
            "inline_value": null,
            "connection": null
          },
          {
            "name": "variable_name",
            "type": "STRING",
            "description": "Name of the case variable to retrieve (must be a valid Python identifier)",
            "required": true,
            "default_value": "",
            "inline_value": "test",
            "connection": null
          }
        ],
        "output_ports": [
          {
            "name": "exec_out",
            "type": "FLOW",
            "description": "Execution flow output",
            "connections": []
          },
          {
            "name": "value",
            "type": "ANY",
            "description": "The value retrieved from the case variable",
            "connections": [
              {
                "source_node_id": "c9424ec9-b93f-4b9a-872f-19a46d941dba",
                "source_port_name": "value",
                "target_node_id": "ad97f148-50e8-4dba-82c9-9e8f3955673d",
                "target_port_name": "message"
              }
            ]
          }
        ],
        "properties": {
          "default_variable_name": "",
          "default_value": null
        }
      },
      {
        "id": "4f0e7fc4-0a29-43e5-b962-008c4533fe84",
        "type": "set_case_variable",
        "name": "Set Case Variable",
        "position": {
          "x": -481.0,
          "y": -178.0
        },
        "input_ports": [
          {
            "name": "exec_in",
            "type": "FLOW",
            "description": "Execution flow input",
            "required": false,
            "default_value": null,
            "inline_value": null,
            "connection": {
              "source_node_id": "a55ef4a1-9c36-4498-a282-9e2da444e73f",
              "source_port_name": "exec_out",
              "target_node_id": "4f0e7fc4-0a29-43e5-b962-008c4533fe84",
              "target_port_name": "exec_in"
            }
          },
          {
            "name": "variable_name",
            "type": "STRING",
            "description": "Name of the case variable to set (must be a valid Python identifier)",
            "required": true,
            "default_value": "",
            "inline_value": "test",
            "connection": null
          },
          {
            "name": "value",
            "type": "ANY",
            "description": "Value to store in the case variable",
            "required": true,
            "default_value": null,
            "inline_value": "tea",
            "connection": null
          }
        ],
        "output_ports": [
          {
            "name": "exec_out",
            "type": "FLOW",
            "description": "Execution flow output",
            "connections": []
          }
        ],
        "properties": {
          "default_variable_name": ""
        }
      },
      {
        "id": "ad97f148-50e8-4dba-82c9-9e8f3955673d",
        "type": "print",
        "name": "Print",
        "position": {
          "x": 160.02249999999998,
          "y": -58.18999999999999
        },
        "input_ports": [
          {
            "name": "exec_in",
            "type": "FLOW",
            "description": "Execution flow input",
            "required": false,
            "default_value": null,
            "inline_value": null,
            "connection": null
          },
          {
            "name": "message",
            "type": "ANY",
            "description": "The message to print (overrides configured message)",
            "required": false,
            "default_value": null,
            "inline_value": null,
            "connection": {
              "source_node_id": "c9424ec9-b93f-4b9a-872f-19a46d941dba",
              "source_port_name": "value",
              "target_node_id": "ad97f148-50e8-4dba-82c9-9e8f3955673d",
              "target_port_name": "message"
            }
          },
          {
            "name": "prefix",
            "type": "STRING",
            "description": "Prefix text to prepend to the message",
            "required": false,
            "default_value": null,
            "inline_value": null,
            "connection": null
          },
          {
            "name": "add_timestamp",
            "type": "BOOLEAN",
            "description": "Whether to include a timestamp with the message",
            "required": false,
            "default_value": null,
            "inline_value": null,
            "connection": null
          }
        ],
        "output_ports": [
          {
            "name": "exec_out",
            "type": "FLOW",
            "description": "Execution flow output",
            "connections": [
              {
                "source_node_id": "ad97f148-50e8-4dba-82c9-9e8f3955673d",
                "source_port_name": "exec_out",
                "target_node_id": "b4ba01ca-94df-4f32-9f4f-e14bacb66aec",
                "target_port_name": "exec_in"
              }
            ]
          },
          {
            "name": "printed_message",
            "type": "STRING",
            "description": "The formatted message that was printed",
            "connections": []
          }
        ],
        "properties": {
          "message": "",
          "prefix": "",
          "add_timestamp": false,
          "add_newline": true
        }
      }
    ],
    "connections": [
      {
        "source_node_id": "a55ef4a1-9c36-4498-a282-9e2da444e73f",
        "source_port_name": "exec_out",
        "target_node_id": "1fcafc89-59ed-4795-93fa-5681d4abb144",
        "target_port_name": "exec_in"
      },
      {
        "source_node_id": "a55ef4a1-9c36-4498-a282-9e2da444e73f",
        "source_port_name": "exec_out",
        "target_node_id": "4f0e7fc4-0a29-43e5-b962-008c4533fe84",
        "target_port_name": "exec_in"
      },
      {
        "source_node_id": "ad97f148-50e8-4dba-82c9-9e8f3955673d",
        "source_port_name": "exec_out",
        "target_node_id": "b4ba01ca-94df-4f32-9f4f-e14bacb66aec",
        "target_port_name": "exec_in"
      },
      {
        "source_node_id": "c9424ec9-b93f-4b9a-872f-19a46d941dba",
        "source_port_name": "value",
        "target_node_id": "ad97f148-50e8-4dba-82c9-9e8f3955673d",
        "target_port_name": "message"
      }
    ]
  }
}