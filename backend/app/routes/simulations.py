"""Financial Simulations API Routes."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Simulation
from app.schemas import SimulationCreateRequest
from app.services.simulation import run_financial_simulation, list_saved_simulations

router = APIRouter(prefix="/api/simulations", tags=["Simulations"])


@router.post("", status_code=status.HTTP_201_CREATED)
def create_simulation(
    payload: SimulationCreateRequest,
    db: Session = Depends(get_db),
):
    """Run and persist a financial what-if simulation."""
    result = run_financial_simulation(db, payload, save_to_db=True)
    return result


@router.get("", status_code=status.HTTP_200_OK)
def get_simulations(db: Session = Depends(get_db)):
    """Retrieve all saved financial simulations."""
    items = list_saved_simulations(db)
    return {
        "simulations": items,
        "total": len(items),
    }


@router.delete("/{sim_id}", status_code=status.HTTP_200_OK)
def delete_simulation(sim_id: int, db: Session = Depends(get_db)):
    """Delete a saved financial simulation by ID."""
    sim = db.query(Simulation).filter(Simulation.id == sim_id).first()
    if not sim:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Simulation with ID {sim_id} not found.",
        )
    db.delete(sim)
    db.commit()
    return {"message": f"Simulation #{sim_id} deleted successfully.", "deleted_id": sim_id}
