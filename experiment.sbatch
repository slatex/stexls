#!/bin/bash
#SBATCH --job-name=ls
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=12G
#SBATCH --exclude=lme49
#SBATCH --gres=gpu:1
#SBATCH -o /home/%u/source/stexls/%x-%j-on-%N.out
#SBATCH -e /home/%u/source/stexls/%x-%j-on-%N.err
#SBATCH --mail-type=ALL
#SBATCH --time=24:00:00

# Initial info
set -e
echo "Your job is running on $(hostname)"

source ~/miniconda3/etc/profile.d/conda.sh
conda activate

echo "python3: $(which python3)"

# Start training
python3 -m stexls.trefier.training --device cuda \
   --epochs 2000 \
   --batch-size 128 \
   --learning-rate 1e-4 \
   --weight-decay 1e-2 \
   --experiment-name test \
   $@

