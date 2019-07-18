import torch
from pytorch_transformers import XLNetTokenizer, XLNetModel

import h5py
import json
import numpy as np
from tqdm import tqdm

disable_cuda = False
if not disable_cuda and torch.cuda.is_available():
    device = torch.device('cuda')
else:
    device = torch.device('cpu')

SPIECE_UNDERLINE = u'▁'

model = XLNetModel.from_pretrained('xlnet-large-cased', output_hidden_states=True).to(device)
tokenizer = XLNetTokenizer.from_pretrained('xlnet-large-cased')

hdf5_filename = '/data/sls/temp/belinkov/contextual-corr-analysis/contextualizers/elmo_original/ptb_pos_dev.hdf5'
output_file_path = '/data/sls/temp/belinkov/contextual-corr-analysis/contextualizers/xlnet_large_cased/ptb_pos_dev.hdf5'

# this follows the HuggingFace API for pytorch-transformers
def get_sentence_repr(sentence, model, tokenizer):
    """
    Get representations for one sentence
    """

    with torch.no_grad():
        ids = tokenizer.encode(sentence)
        input_ids = torch.tensor([ids]).to(device)
        # Hugging Face format: list of torch.FloatTensor of shape (batch_size, sequence_length, hidden_size) (hidden_states at output of each layer plus initial embedding outputs)
        all_hidden_states = model(input_ids)[-1]
        # convert to format required for contexteval: numpy array of shape (num_layers, sequence_length, representation_dim)
        all_hidden_states = [hidden_states[0].cpu().numpy() for hidden_states in all_hidden_states[:-1]]
        all_hidden_states = np.array(all_hidden_states)

    #For each word, take the representation of its last sub-word
    segmented_tokens = tokenizer.convert_ids_to_tokens(ids)
    assert len(segmented_tokens) == all_hidden_states.shape[1], 'incompatible tokens and states'
    mask = np.full(len(segmented_tokens), False)
    # if next token is a new word, take current token's representation
    #print(segmented_tokens)
    for i in range(len(segmented_tokens)-1):
        if segmented_tokens[i+1].startswith(SPIECE_UNDERLINE):
            #print(i)
            mask[i] = True
        # always take the last token representation for the last word
    mask[-1] = True
    all_hidden_states = all_hidden_states[:, mask]

    return all_hidden_states


def get_sentences_from_hdf5(hdf5_filename):

    hdf5 = h5py.File(hdf5_filename)
    sentence_to_idx = json.loads(hdf5['sentence_to_idx'][0])
    sentences = []
    for s in sentence_to_idx:
        sentences.append(s)

    return sentences, sentence_to_idx


# from https://github.com/nelson-liu/contextual-repr-analysis
def make_hdf5_file(sentence_to_index, vectors, output_file_path):
    with h5py.File(output_file_path, 'w') as fout:
        for key, embeddings in vectors.items():
            fout.create_dataset(
                str(key),
                embeddings.shape, dtype='float32',
                data=embeddings)
        sentence_index_dataset = fout.create_dataset(
            "sentence_to_index",
            (1,),
            dtype=h5py.special_dtype(vlen=str))
        sentence_index_dataset[0] = json.dumps(sentence_to_index)


def run(hdf5_filename, model, tokenizer, output_file_path):

    print('reading sentences from hdf5')
    hdf5 = h5py.File(hdf5_filename)
    sentence_to_idx = json.loads(hdf5['sentence_to_index'][0])
    hdf5.close()
    idx_to_repr = dict()

    print('getting repreesntations from model')
    for s, idx in tqdm(sentence_to_idx.items(), desc='repr'):
        hidden_states = get_sentence_repr(s, model, tokenizer)
        idx_to_repr[idx] = hidden_states

    print('writing representations to new hdf5')
    make_hdf5_file(sentence_to_idx, idx_to_repr, output_file_path)


if __name__ == '__main__':
    run(hdf5_filename, model, tokenizer, output_file_path)
