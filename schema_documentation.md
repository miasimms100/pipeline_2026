# Database Schema Documentation

## Tourism and Weather Forecast Data Warehouse

This database stores tourism attraction information and daily weather forecast data loaded into a PostgreSQL database hosted in Supabase.

The schema is normalized to approximately Third Normal Form (3NF) by:

- separating entities into related tables
- avoiding repeated data
- using bridge tables for many-to-many relationships

---
### ER Diagram

![Weather ER Diagram](<Weather_App_ERD.png>)

## Database Overview

The database contains six tables:

- `weather_code`
- `weather_forecast`
- `location`
- `attraction`
- `category`
- `attraction_category`

### Entity Relationship Summary

| Table | Purpose |
| --- | --- |
| `weather_code` | Stores standardized WMO weather condition codes and descriptions |
| `weather_forecast` | Stores daily weather forecast metrics |
| `location` | Stores unique physical addresses |
| `attraction` | Stores tourism attraction details |
| `category` | Stores tourism category types |
| `attraction_category` | Bridge table connecting attractions to categories |

---

## Table Documentation

### 1. `weather_code`

**Purpose**

Stores standardized WMO (World Meteorological Organization) weather interpretation codes with categorization and severity information.

**Example**

- Code `0` = Clear sky, Clear category, Severity 1
- Code `61` = Rain: Slight intensity, Rain category, Severity 1
- Code `80` = Showers: Moderate intensity, Showers category, Severity 3

**Primary Key**

- `weather_code`

**Relationships**

- One `weather_code` can relate to many `weather_forecast` records.
- Referenced by `weather_forecast.weather_code_id`.

**Table Structure**

| Column Name | Data Type | Key | Description |
| --- | --- | --- | --- |
| `weather_code` | `INTEGER` | Primary Key | Unique WMO weather condition code (0-100) |
| `weather_category` | `TEXT` |  | Category/type of weather (e.g., Clear, Clouds, Rain, Snow, Fog) |
| `weather_description` | `TEXT` |  | Detailed description of the weather condition |
| `severity_level` | `INTEGER` |  | Severity indicator (1=light/clear, 2=moderate, 3=heavy/severe) |
| `assets` | `TEXT` |  | Asset filename for weather icon/image matching the conditions |

---

### 2. `weather_forecast`

**Purpose**

Stores daily weather forecast information from the Open-Meteo API.

**Forecast data includes**

- temperatures
- precipitation
- sunrise and sunset
- UV index
- daylight duration

**Primary Key**

- `forecast_id`

**Foreign Keys**

- `weather_code_id` → `weather_code.weather_code`

**Relationships**

- Many forecasts can reference one weather code.
- Each forecast date is unique.

**Table Structure**

| Column Name | Data Type | Key | Description |
| --- | --- | --- | --- |
| `forecast_id` | `BIGSERIAL` | Primary Key | Auto-generated forecast record ID |
| `forecast_date` | `DATE` | Unique | Date of the forecast |
| `weather_code_id` | `INTEGER` | Foreign Key | Weather condition code for the forecast |
| `temperature_max` | `DOUBLE PRECISION` |  | Maximum daily temperature |
| `temperature_min` | `DOUBLE PRECISION` |  | Minimum daily temperature |
| `sunrise` | `TIME` |  | Sunrise time |
| `sunset` | `TIME` |  | Sunset time |
| `precipitation_sum` | `DOUBLE PRECISION` |  | Total daily precipitation |
| `precipitation_hours` | `DOUBLE PRECISION` |  | Hours with precipitation |
| `precipitation_probability_max` | `INTEGER` |  | Maximum precipitation probability |
| `daylight_duration` | `DOUBLE PRECISION` |  | Daylight duration in seconds |
| `sunshine_duration` | `DOUBLE PRECISION` |  | Sunshine duration in seconds |
| `uv_index_max` | `DOUBLE PRECISION` |  | Maximum UV index |

---

### 3. `location`

**Purpose**

Stores unique attraction addresses and geographic location information.

This table removes duplicate address information from attractions and supports normalization.

**Primary Key**

- `location_id`

**Relationships**

- One location can contain many attractions.
- Referenced by `attraction.location_id`.

**Constraints**

- Unique combination of `street_address`, `city`, and `state`.

**Table Structure**

| Column Name | Data Type | Key | Description |
| --- | --- | --- | --- |
| `location_id` | `INTEGER` | Primary Key | Unique location identifier |
| `street_address` | `TEXT` |  | Attraction street address |
| `city` | `TEXT` |  | Attraction city |
| `state` | `TEXT` |  | Attraction state |

---

### 4. `attraction`

**Purpose**

Stores tourism attraction information and business details.

**Examples**

- museums
- parks
- entertainment venues
- recreational attractions

**Primary Key**

- `attraction_id`

**Foreign Keys**

- `location_id` → `location.location_id`

**Relationships**

- Many attractions can belong to one location.
- Many attractions can belong to many categories through `attraction_category`.

**Table Structure**

| Column Name | Data Type | Key | Description |
| --- | --- | --- | --- |
| `attraction_id` | `INTEGER` | Primary Key | Unique attraction identifier |
| `attraction_name` | `TEXT` |  | Attraction name |
| `phone_number` | `TEXT` |  | Contact phone number |
| `website` | `TEXT` |  | Attraction website URL |
| `is_indoor` | `BOOLEAN` |  | Whether the attraction is indoors |
| `adult_only` | `BOOLEAN` |  | Whether the attraction is for adults only |
| `location_id` | `INTEGER` | Foreign Key | Link to the attraction location |

---

### 5. `category`

**Purpose**

Stores tourism activity categories used to classify attractions.

**Categories loaded from ETL**

- `water`
- `play_sweat_it_out`
- `small_kid_friendly_under_10`
- `big_kid_friendly_over_10`
- `culture`
- `nature`

**Primary Key**

- `category_id`

**Relationships**

- One category can relate to many attractions through `attraction_category`.

**Table Structure**

| Column Name | Data Type | Key | Description |
| --- | --- | --- | --- |
| `category_id` | `INTEGER` | Primary Key | Unique category identifier |
| `category_name` | `TEXT` | Unique | Category name |

---

### 6. `attraction_category`

**Purpose**

Bridge table implementing the many-to-many relationship between attractions and categories.

**Details**

- An attraction can belong to multiple categories.
- A category can contain multiple attractions.

**Example**

A park may be both `nature` and `small_kid_friendly_under_10`.

**Composite Primary Key**

- (`attraction_id`, `category_id`)

**Foreign Keys**

- `attraction_id` → `attraction.attraction_id`
- `category_id` → `category.category_id`

**Relationships**

- Many-to-many relationship between attractions and categories.

**Table Structure**

| Column Name | Data Type | Key | Description |
| --- | --- | --- | --- |
| `attraction_id` | `INTEGER` | Composite PK / FK | Attraction identifier |
| `category_id` | `INTEGER` | Composite PK / FK | Category identifier |

---

## Cardinality Relationships

| Parent Table | Child Table | Relationship Type |
| --- | --- | --- |
| `weather_code` | `weather_forecast` | One-to-Many |
| `location` | `attraction` | One-to-Many |
| `attraction` | `attraction_category` | One-to-Many |
| `category` | `attraction_category` | One-to-Many |
| `attraction` ↔ `category` | Through `attraction_category` | Many-to-Many |

---

## Normalization Notes (3NF)

This schema is normalized to approximately Third Normal Form:

- Repeating location information is separated into `location`.
- Weather descriptions are separated into `weather_code`.
- Categories are separated into `category`.
- The many-to-many relationship is resolved with `attraction_category`.
- Non-key columns depend only on each table's primary key.

---

## Data Sources

### Weather Data Source

Weather forecast data is sourced from the Open-Meteo API.

The API provides:

- daily forecasts
- weather condition codes
- precipitation data
- temperature data
- UV index data
- sunrise and sunset times

Weather condition codes follow WMO Weather Interpretation standards.

### Tourism Data Source

Tourism attraction data is sourced from CSV files containing:

- attraction information
- addresses
- contact information
- tourism activity classifications

---

## Example Relationship Flow

- `weather_forecast.weather_code_id = 61`
- `weather_code.weather_code_id = 61`
- Description returned: "Rain: Slight, moderate and heavy intensity"

This design prevents duplicate weather descriptions from being stored repeatedly in the forecast table.
