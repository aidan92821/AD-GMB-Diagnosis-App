import pandas as pd

forward = pd.read_csv("demux_summary/forward-seven-number-summaries.tsv", sep='\t')
reverse = pd.read_csv("demux_summary/reverse-seven-number-summaries.tsv", sep='\t')

# transpose to get the percentiles as columns
forward = forward.T
reverse = reverse.T

# clean up the columns
forward.columns = forward.iloc[0]
forward = forward.iloc[1:, :]
reverse.columns = reverse.iloc[0]
reverse = reverse.iloc[1:, :]

# acceptable quality threshold lower bound
QUALITY_THRESHOLD = 25

logical_forward = (forward['50%'] <= QUALITY_THRESHOLD).tolist()
logical_forward.reverse()
logical_reverse = (reverse['50%'] <= QUALITY_THRESHOLD).tolist()
logical_reverse.reverse()

forward_indices = {boolean : i for boolean, i in zip(logical_forward, range(1,forward.shape[0]))}
reverse_indices = {boolean : i for boolean, i in zip(logical_reverse, range(1,reverse.shape[0]))}

if True in forward_indices:
    trunc_len_forward = forward_indices[True]
else:
    trunc_len_forward = forward.shape[0]

if True in reverse_indices:
    trunc_len_reverse = reverse_indices[True]
else:
    trunc_len_reverse = reverse.shape[0]

print(trunc_len_forward, trunc_len_reverse)