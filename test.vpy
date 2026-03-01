{
  "format_version": "1.0.0",
  "file_type": "visualpython_project",
  "graph": {
    "id": "292cd8ff-f5fd-411e-979c-ca811e28e8fc",
    "metadata": {
      "name": "test2",
      "description": "Subworkflow created from selection",
      "author": "",
      "version": "1.0.0",
      "created_at": "2026-01-31T02:21:20.960007",
      "modified_at": "2026-01-31T02:34:35.435884",
      "tags": [
        "subworkflow",
        "auto-generated"
      ]
    },
    "nodes": [
      {
        "id": "d363c3b0-8e0c-49e0-ab16-4ba90d768d2d",
        "type": "print",
        "name": "Print",
        "position": {
          "x": 100.0,
          "y": 0.0
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
              "source_node_id": "89cbcbf9-0bde-4075-8d5a-8ad38459f651",
              "source_port_name": "exec_out",
              "target_node_id": "d363c3b0-8e0c-49e0-ab16-4ba90d768d2d",
              "target_port_name": "exec_in"
            }
          },
          {
            "name": "message",
            "type": "ANY",
            "description": "The message to print (overrides configured message)",
            "required": false,
            "default_value": null,
            "inline_value": 2,
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
          "message": "",
          "prefix": "",
          "add_timestamp": false,
          "add_newline": true
        }
      },
      {
        "id": "d41af6c0-c917-4ebb-b250-27e73c471284",
        "type": "subgraph_input",
        "name": "Subgraph Input",
        "position": {
          "x": -183.0,
          "y": 203.0
        },
        "input_ports": [],
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
            "description": "Value received from subgraph input 'input'",
            "connections": []
          }
        ],
        "properties": {
          "port_name": "input",
          "port_type": "ANY",
          "description": "",
          "default_value": null
        }
      },
      {
        "id": "89cbcbf9-0bde-4075-8d5a-8ad38459f651",
        "type": "start",
        "name": "Start",
        "position": {
          "x": -322.0,
          "y": -3.0
        },
        "input_ports": [],
        "output_ports": [
          {
            "name": "exec_out",
            "type": "FLOW",
            "description": "Execution flow output - start of script execution",
            "connections": [
              {
                "source_node_id": "89cbcbf9-0bde-4075-8d5a-8ad38459f651",
                "source_port_name": "exec_out",
                "target_node_id": "d363c3b0-8e0c-49e0-ab16-4ba90d768d2d",
                "target_port_name": "exec_in"
              }
            ]
          }
        ],
        "properties": {}
      }
    ],
    "connections": [
      {
        "source_node_id": "89cbcbf9-0bde-4075-8d5a-8ad38459f651",
        "source_port_name": "exec_out",
        "target_node_id": "d363c3b0-8e0c-49e0-ab16-4ba90d768d2d",
        "target_port_name": "exec_in"
      }
    ]
  }
}