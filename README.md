
# Fruit Store Inventory API

A simple RESTful API built with FastAPI for managing a fruit store inventory. This API supports CRUD operations to add, view, update, and delete fruits in the inventory.

## Features

- **View all fruits**: Get a list of all fruits in the inventory.
- **View a specific fruit**: Retrieve details of a fruit by its ID.
- **Add a new fruit**: Add a fruit with details like name, price per kg, and quantity.
- **Update fruit details**: Modify information of an existing fruit.
- **Delete a fruit**: Remove a fruit from the inventory.

## Requirements

- Python 3.8 or higher
- FastAPI
- Uvicorn

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/RezaNoel/FastAPI.git
   cd FastAPI
   ```

2. Install dependencies:
   ```bash
   pip install fastapi uvicorn
   ```

## Running the API

1. Start the server:
   ```bash
   python -m uvicorn app:app --reload
   ```

2. Access the API in your browser or API testing tools (like Postman):
   - Base URL: `http://127.0.0.1:8000`
   - Interactive API Documentation:
     - Swagger UI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
     - ReDoc: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

## API Endpoints

| Method | Endpoint          | Description                     |
|--------|-------------------|---------------------------------|
| GET    | `/fruits`         | Get a list of all fruits        |
| GET    | `/fruits/{id}`    | Get details of a specific fruit |
| POST   | `/fruits`         | Add a new fruit                 |
| PUT    | `/fruits/{id}`    | Update an existing fruit        |
| DELETE | `/fruits/{id}`    | Delete a fruit                  |

## Example Request

### Add a Fruit

**POST** `/fruits`

**Body:**
```json
{
  "id": 1,
  "name": "Apple",
  "price_per_kg": 3.5,
  "quantity_in_kg": 10
}
```

**Response:**
```json
{
  "id": 1,
  "name": "Apple",
  "price_per_kg": 3.5,
  "quantity_in_kg": 10
}
```

## License

This project is licensed under the MIT License.

---

Feel free to contribute by submitting issues or pull requests!
