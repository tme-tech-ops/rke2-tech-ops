"""check_drift for nodes that only do something when the deployment is installed.

They never drift, so a deployment update never re-runs or reinstalls them.
Read-only.
"""
from dell import ctx

ctx.logger.info(f"{ctx.node.id}: no drift (only runs when this deployment is installed)")
ctx.returns(None)
