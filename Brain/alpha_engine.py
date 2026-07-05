import os
import sys
import importlib.util
import logging
import traceback
import time
import pandas as pd
from typing import Dict, Any, List, Callable, Optional

logger = logging.getLogger("QuantPlatform.AlphaEngine")

class AlphaEngine:
    """
    Scans the Strategies/ directory, validates alpha metadata, respects warmup periods,
    and runs alpha compute functions independently.
    """
    def __init__(self, alphas_dir: str = "Strategies"):
        self.alphas_dir = alphas_dir
        os.makedirs(self.alphas_dir, exist_ok=True)
        self.alphas: Dict[str, Dict[str, Any]] = {}

    def discover_alphas(self) -> List[str]:
        """Scans the Strategies/ directory recursively for python files and loads their module info."""
        sys.path.insert(0, os.path.abspath(self.alphas_dir))

        discovered = []
        for root, _dirs, files in os.walk(self.alphas_dir):
            for filename in files:
                if not filename.endswith(".py") or filename.startswith("__") or filename == "base.py":
                    continue
                module_name = filename[:-3]
                file_path = os.path.join(root, filename)

                if module_name in self.alphas:
                    logger.warning(f"Skipping duplicate module name '{module_name}' at {file_path}")
                    continue

                try:
                    # Dynamically load the module
                    spec = importlib.util.spec_from_file_location(module_name, file_path)
                    if spec is None or spec.loader is None:
                        logger.error(f"Failed to create spec for {filename}")
                        continue

                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    # Validate alpha interface
                    if not hasattr(module, "compute") or not callable(module.compute):
                        logger.error(f"Alpha {filename} is missing 'compute(panel)' callable function.")
                        continue

                    if not hasattr(module, "__alpha_meta__") or not isinstance(module.__alpha_meta__, dict):
                        logger.error(f"Alpha {filename} is missing '__alpha_meta__' metadata dictionary.")
                        continue

                    meta = module.__alpha_meta__

                    # Resolve alternative metadata keys for flexibility
                    if "name" not in meta and "id" in meta:
                        meta["name"] = meta["id"]
                    elif "name" not in meta:
                        meta["name"] = module_name

                    if "warmup_period" not in meta and "min_warmup_bars" in meta:
                        meta["warmup_period"] = meta["min_warmup_bars"]
                    elif "warmup_period" not in meta:
                        meta["warmup_period"] = 20

                    # Recheck required properties
                    if "name" not in meta or "warmup_period" not in meta:
                        logger.error(f"Alpha {filename} is missing metadata elements.")
                        continue

                    self.alphas[module_name] = {
                        "module": module,
                        "meta": meta,
                        "compute_fn": module.compute,
                        "file_path": file_path
                    }
                    discovered.append(module_name)
                    logger.info(f"Loaded alpha: {meta['name']} (from {file_path}) with warmup {meta['warmup_period']} days.")

                except Exception as e:
                    logger.error(f"Failed to import alpha file {filename}: {e}\n{traceback.format_exc()}")

        return discovered

    def run_alpha(self, name: str, panel: Dict[str, pd.DataFrame]) -> Optional[pd.DataFrame]:
        """
        Executes a single alpha on the provided data panel.
        Handles exceptions internally to avoid breaking execution.
        """
        if name not in self.alphas:
            logger.error(f"Alpha {name} is not loaded.")
            return None
            
        alpha_info = self.alphas[name]
        meta = alpha_info["meta"]
        compute_fn = alpha_info["compute_fn"]
        
        logger.info(f"Executing alpha: {meta['name']}...")
        start_time = time.time()
        
        try:
            # Execute alpha compute function
            factor_scores = compute_fn(panel)
            
            # Basic validation of the outputs
            if not isinstance(factor_scores, pd.DataFrame):
                logger.error(f"Alpha {name} did not return a pandas DataFrame. Got {type(factor_scores)}")
                return None
                
            if factor_scores.empty:
                logger.warning(f"Alpha {name} returned an empty DataFrame.")
                return None
                
            # Verify structure aligns with input panel (e.g. index is dates, columns are symbols)
            close_df = panel["close"]
            # Verify columns match (at least overlap)
            common_cols = factor_scores.columns.intersection(close_df.columns)
            if len(common_cols) == 0:
                logger.error(f"Alpha {name} factor columns do not overlap with panel symbols.")
                return None
                
            elapsed = time.time() - start_time
            logger.info(f"Alpha {name} completed successfully in {elapsed:.3f} seconds.")
            return factor_scores
            
        except Exception as e:
            logger.error(f"Exception raised while running alpha {name}: {e}\n{traceback.format_exc()}")
            return None

    def run_all(self, panel: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        """
        Runs all loaded alphas on the panel, returning a dict of factor scores.
        """
        results = {}
        for name in list(self.alphas.keys()):
            scores = self.run_alpha(name, panel)
            if scores is not None:
                results[name] = scores
        return results
