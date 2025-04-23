# Databricks DDL Generator

A Streamlit application that generates DDL (Data Definition Language) statements for Databricks based on a physical data model JSON. Optimized to handle Databricks-specific constraints and naming conventions.

## Video Demonstration

Watch a quick demonstration of how to use the Databricks DDL Generator:

🎬 [View Video Tutorial](https://screen.studio/share/kuIJzmMO)

This video shows the app in action, including how to import a model from Ellie.ai and generate Databricks-compatible DDL.

## Features

- Parse physical data model JSON from file or directly from the Ellie.ai API
- Generate Databricks-compliant DDL statements
- Support for primary and foreign key constraints (informational only in Databricks)
- Data type mapping and column/table comments
- Multiple constraint definition approaches (ALTER TABLE statements or comments)
- Optional data validation query examples
- Download generated DDL as SQL file

## Identifier Handling

The application provides a methog to handle identifiers (table and column names) that contain spaces or special characters:

**Underscore (Recommended for Databricks)**: Replaces spaces and special characters with underscores
   - Example: "Address ID" → "Address_ID"
   - This is the safest option for Databricks Delta tables and is enabled by default

**Note**: Databricks Delta tables have a limitation that column names cannot contain spaces or special characters, resulting in errors like:
```
[DELTA_INVALID_CHARACTERS_IN_COLUMN_NAMES] Found invalid character(s) among ' ,;{}()\n\t=' in the column names of your schema.
```
To avoid this error, keep the "Replace spaces with underscores" option enabled (selected by default).

## Project Structure

```
.
├── app.py                  # Main Streamlit application
├── README.md               # Project documentation
├── requirements.txt        # Python dependencies
├── run.sh                  # Shell script to run the application
├── test.py                 # Test and example code
└── physicaldatamodel.json  # Sample data model for testing
```

## Installation

1. Clone this repository:
```bash
git clone https://github.com/BroStas/ellie-databricks-generator-python-script.git
cd ellie-databricks-generator-python-script
```

2. Install the required dependencies:
```bash
pip install -r requirements.txt
```

Alternatively, you can use the provided shell script to both install dependencies and run the application:
```bash
chmod +x run.sh
./run.sh
```

## Usage

1. Run the Streamlit application:
```bash
streamlit run app.py
```

2. Access the application in your web browser at http://localhost:8501

3. Choose one of the following options to provide your physical data model:
   - **Direct JSON input**: Paste your physical data model JSON directly or use the "Load Sample" button
   - **Fetch from Ellie.ai API**: Enter your Model ID and API Token to fetch the model directly

4. Configure DDL options as needed:
   - Create database: Generate a CREATE DATABASE statement
   - Include primary keys: Add PRIMARY KEY constraints
   - Use Delta format: Specify USING DELTA in table creation
   - Constraint approach: Choose between ALTER TABLE statements or comments
   - Other options: Validation queries, column formats, etc.

5. Click the "Generate DDL" button to create the Databricks DDL statements

6. Review the generated DDL and download it if satisfied

### Fetching from Ellie.ai API

To fetch a physical data model directly from Ellie.ai:

1. Click on the "Fetch from Ellie.ai API" tab
2. Enter your Model ID (the numeric identifier of your model)
3. Enter your API Token (used for authentication)
4. Optionally, change the Environment value (defaults to "templates", but can be changed to "app" or another environment slug)
5. Click "Fetch Model"

The JSON will be fetched and loaded automatically. You can then proceed to generate the DDL statements.

## Constraint Support in Databricks

### Important Note About Databricks Constraints

In Databricks, primary key and foreign key constraints serve primarily as **informational constructs** rather than enforced rules. This means:

1. These constraints document relationships between tables
2. They are NOT enforced by Databricks
3. It's possible to insert data that violates these constraints without triggering errors
4. They may be used for query optimization, but do not guarantee data integrity

### Constraint Approaches

This application supports two methods of defining constraints:

1. **ALTER TABLE Statements**: Define constraints using separate ALTER TABLE statements after table creation
   ```sql
   CREATE TABLE Order (
     order_id BIGINT NOT NULL,
     customer_id BIGINT NOT NULL
   );
   
   ALTER TABLE Order ADD CONSTRAINT pk_order PRIMARY KEY (order_id);
   ALTER TABLE Order ADD CONSTRAINT fk_order_customer FOREIGN KEY (customer_id) REFERENCES Customer(customer_id);
   ```

2. **Comments Only**: Include relationships as SQL comments (useful for documentation without formal constraints)
   ```sql
   -- Foreign Key Relationship: Order.customer_id references Customer.customer_id
   ```

Note: Databricks recommends using ALTER TABLE statements after table creation, as adding constraints directly in CREATE TABLE statements can sometimes lead to issues.

### Data Validation

Since Databricks does not enforce constraints, the application can generate example validation queries to help you maintain data integrity:

```sql
-- Validate primary key uniqueness
SELECT id, COUNT(*) as count
FROM table
GROUP BY id
HAVING COUNT(*) > 1;

-- Validate foreign key integrity
SELECT child.*
FROM child_table child
LEFT JOIN parent_table parent ON child.parent_id = parent.id
WHERE child.parent_id IS NOT NULL
  AND parent.id IS NULL;
```

Consider implementing these validations in your ETL pipelines or using Delta Live Tables (DLT) expectations for more robust data integrity.

## Data Model JSON Format

The application expects a JSON in the following format:

```json
{
  "model": {
    "modelId": 123,
    "name": "Model Name",
    "description": "Model Description",
    "entities": [
      {
        "id": "entity-id",
        "name": "Entity_Name",
        "metadata": {
          "Description": "Entity description"
        },
        "attributes": [
          {
            "name": "column_name",
            "metadata": {
              "PK": true,
              "FK": false,
              "Not null": true,
              "Data type": "BIGINT",
              "description": "Column description"
            }
          }
        ]
      }
    ],
    "relationships": [
      {
        "sourceEntity": {
          "name": "Source_Entity",
          "attributeNames": ["source_column"]
        },
        "targetEntity": {
          "name": "Target_Entity",
          "attributeNames": ["target_column"] 
        }
      }
    ]
  }
}
```

## Troubleshooting

### Common Issues

1. **API Fetch Not Working**: 
   - Check that your Model ID and API Token are correct
   - Ensure the Environment slug is set properly
   - Verify you have internet access and the Ellie.ai API is reachable

2. **JSON Parse Error**: 
   - Make sure your JSON is valid and properly formatted
   - Use the "Load Sample" button to see an example of the expected format

3. **Missing Dependencies**:
   - Run `pip install -r requirements.txt` to ensure all dependencies are installed

4. **Constraints Not Being Created**:
   - Verify you have the "Include primary keys" option checked
   - Check the "Constraint Approach" setting

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT 