#!/bin/zsh
set -e

# IMPORTANT RUNNING DIRECTIONS:
# make sure script is executable with chmod 744
# run using ./qiime2_process.sh

# initialize conda for script shell
source "$(conda info --base)/etc/profile.d/conda.sh"

# activate the environment
conda activate qiime2-amplicon-2024.10

# download the taxa classifier if it doesn't exist where expected
if [ ! -f ../taxa_classifier/silva-138-99-nb-classifier.qza ]; then
  echo "downloading taxa classifier"
  wget -P ../taxa_classifier https://data.qiime2.org/classifiers/sklearn-1.4.2/silva/silva-138-99-nb-classifier.qza
else
  echo "taxa classifier already exists, skipping download"
fi

# change directories to where the qiime files will be stored
cd ../data/qiime_files

# import the sampes into qiime2
echo "importing samples into qiime2"
qiime tools import \
  --type 'SampleData[PairedEndSequencesWithQuality]' \
  --input-path manifest.tsv \
  --output-path demux.qza \
  --input-format PairedEndFastqManifestPhred33V2 \

# get summary statistics per position and export it
# this is so you know where to truncate
echo "getting summary statistics"
qiime demux summarize \
  --i-data demux.qza \
  --o-visualization demux.qzv

qiime tools export \
  --input-path demux.qzv \
  --output-path demux_summary

# run the python script that finds where the median
# scores drop to under 25 for each forward/reverse read (the pos to truncate)
echo "getting truncate lengths"
output=$(python3 /Users/emmagomez/code/capstone/ml/gmb/scripts/qc.py)
trunc_forward="$(echo "$output" | cut -d' ' -f1)"
trunc_reverse="$(echo "$output" | cut -d' ' -f2)"

# denoise using DADA2
# make sure you have at least 8 cores for --p-n-threads 8 to work
echo "denoising with DADA2. this may take several minutes. (for 37 runs it took 80 minutes)"
qiime dada2 denoise-paired \
  --i-demultiplexed-seqs demux.qza \
  --p-trim-left-f 17 \
  --p-trim-left-r 21 \
  --p-trunc-len-f $trunc_forward \
  --p-trunc-len-r $trunc_reverse \
  --p-n-threads 8 \
  --o-table table.qza \
  --o-representative-sequences rep-seqs.qza \
  --o-denoising-stats stats.qza

# classify taxa
echo "classifying taxa"
qiime feature-classifier classify-sklearn \
  --i-classifier ../../taxa_classifier/silva-138-99-nb-classifier.qza \
  --i-reads rep-seqs.qza \
  --o-classification taxonomy.qza

# collapse from ASV table to genus level
echo "collapsing to genus level"
qiime taxa collapse \
  --i-table table.qza \
  --i-taxonomy taxonomy.qza \
  --p-level 6 \
  --o-collapsed-table genus-table.qza

# normalize to get relative abundance
echo "normalizing abundance counts"
qiime feature-table relative-frequency \
  --i-table genus-table.qza \
  --o-relative-frequency-table genus-relfreq.qza

# export to a BIOM file
echo "exporting to BIOM"
qiime tools export \
  --input-path genus-relfreq.qza \
  --output-path exported-genus

# convert to tsv for python
echo "converting to tsv"
biom convert \
  -i exported-genus/feature-table.biom \
  -o genus-table.tsv \
  --to-tsv

# delete the intermediate files
rm -r demux_summary

echo done