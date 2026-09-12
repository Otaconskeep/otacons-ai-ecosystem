import argparse
from pathlib import Path
from core.platform import detect
from core.planner import recommend_hardware_plan
from core.config import build_config,save
def build_plan(name,features): return build_config(recommend_hardware_plan(detect()),name,features)
def main():
 p=argparse.ArgumentParser(); p.add_argument('--name',default='Assistant'); p.add_argument('--features',default='chat,memory'); p.add_argument('--output',default=str(Path.home()/'.config/otacon')); a=p.parse_args(); print(f'Wrote {save(build_plan(a.name,[x for x in a.features.split(",") if x]),Path(a.output))}')
if __name__=='__main__': main()
