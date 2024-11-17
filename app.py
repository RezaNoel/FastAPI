from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List

app = FastAPI()

# Data model for a fruit
class Fruit(BaseModel):
    id: int
    name: str
    price_per_kg: float
    quantity_in_kg: float

# Temporary in-memory database
inventory = []

# Get the list of all fruits
@app.get("/fruits", response_model=List[Fruit])
def get_all_fruits():
    return inventory

# Get details of a specific fruit by ID
@app.get("/fruits/{fruit_id}", response_model=Fruit)
def get_fruit(fruit_id: int):
    for fruit in inventory:
        if fruit.id == fruit_id:
            return fruit
    raise HTTPException(status_code=404, detail="Fruit not found")

# Add a new fruit to the inventory
@app.post("/fruits", response_model=Fruit)
def add_fruit(fruit: Fruit):
    for existing_fruit in inventory:
        if existing_fruit.id == fruit.id:
            raise HTTPException(status_code=400, detail="Fruit with this ID already exists")
    inventory.append(fruit)
    return fruit

# Update information of an existing fruit
@app.put("/fruits/{fruit_id}", response_model=Fruit)
def update_fruit(fruit_id: int, updated_fruit: Fruit):
    for index, fruit in enumerate(inventory):
        if fruit.id == fruit_id:
            inventory[index] = updated_fruit
            return updated_fruit
    raise HTTPException(status_code=404, detail="Fruit not found")

# Delete a fruit from the inventory
@app.delete("/fruits/{fruit_id}")
def delete_fruit(fruit_id: int):
    for index, fruit in enumerate(inventory):
        if fruit.id == fruit_id:
            del inventory[index]
            return {"message": "Fruit deleted successfully"}
    raise HTTPException(status_code=404, detail="Fruit not found")
