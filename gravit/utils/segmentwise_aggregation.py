import os
import glob
import numpy as np
import argparse

from gravit.utils.parser import get_args, get_cfg
import sys
sys.path.append('/home/juro4948/gravit/data/egoexo4d')
from preprocess_utils import *
from gravit.utils.data_loader import load_labels, load_labels_raw, get_segment_labels_by_batch_idxs, load_batch_indices
# load_and_fuse_modalities, load_labels, crop_to_start_and_end, get_segments_and_batch_idxs
"""
Script to convert framewise features and labels to segmentwise features and labels.
"""



def remove_action_indices(labels, features):    
    # Find the indices of 'action_start' and 'action_end' in labels
    start_indices = [i for i, label in enumerate(labels) if label == actions['action_start']]
    end_indices = [i for i, label in enumerate(labels) if label == actions['action_end']]
    
    # Remove the corresponding indices from labels and features
    labels = [label for i, label in enumerate(labels) if i not in start_indices and i not in end_indices]
    features = [feature for i, feature in enumerate(features) if i not in start_indices and i not in end_indices]
    
    return labels, np.array(features)


if __name__ == "__main__":
    root_data = './data'

    # Load non-segmented features and labels
    features = 'omnivore-trimmed-ego' #'egoexo-brp-level4' #'omnivore-ego' # name of the directory in data/features/ that are framewise
    output_features_dir = 'omnivore-segmentwise-ego' # name of the output directory in data/features/
    features_exo = 'omnivore-trimmed-ego-exo' 
    output_features_dir_exo = 'omnivore-segmentwise-ego-exo'
    save_features = False

    dataset =  'egoexo-regular-all-categories' #  name of corresponding annotation dataset in data/annotations/
    output_annotations_dir = 'egoexo-segmentwise-all-categories' # name of the output directory in data/annotations/
    save_labels = True
    annotation_type =  'descriptions' #'groundTruth' #'descriptions' #
    batch_idx_path = f"/local/juro4948/data/egoexo4d/gravit_data/data_new/annotations/{dataset}/batch_idx/"

    crop_start_end = False

    ##########################################
        

    output_dir_path = os.path.join(root_data, f'annotations/{output_annotations_dir}/')
    if annotation_type == 'descriptions':
        load_descriptions = True
    else:
        load_descriptions = False


    if not os.path.exists(output_dir_path):
        print(f'Output directory does not exist: {output_dir_path}')
        user_input = input(f"Create the output directory named {output_annotations_dir} and it must contain the splits/ and mapping.txt files. Is this done? (Y/N) ")
        if user_input.lower() != 'y':
            print('Exiting...')
            exit()
        if not os.path.exists(output_dir_path):
            print(f'Output directory does not exist: {output_dir_path}')
            print('Exiting...')
            exit()
        if not os.path.exists(os.path.join(output_dir_path, 'splits')):
            print(f'Output directory does not contain splits/ directory: {output_dir_path}')
            print('Exiting...')
            exit()
        if not os.path.exists(os.path.join(output_dir_path, 'mapping.txt')):
            print(f'Output directory does not contain mapping.txt file: {output_dir_path}')
            print('Exiting...')
            exit()

    if save_labels:
        # make new directory if groundTruth folder already exist
        if os.path.exists(os.path.join(output_dir_path, annotation_type)):
            import shutil
            shutil.rmtree(os.path.join(output_dir_path, annotation_type))
            print(f'Removing existing {annotation_type} directory: os.path.join(output_dir_path, annotation_type)')
        os.makedirs(os.path.join(output_dir_path, annotation_type))

    # Build a mapping from action classes to action ids
    # actions = {}
    # with open(os.path.join(root_data, f'annotations/{dataset}/mapping.txt')) as f:
    #     for line in f:
    #         aid, cls = line.strip().split(' ')
    #         actions[cls] = int(aid)
    # reverse = {}
    # for k, v in actions.items():
    #     reverse[v] = k
    actions = []


    # Get a list of all video ids
    all_ids = sorted([os.path.splitext(v)[0] for v in os.listdir(os.path.join(root_data, f'annotations/{dataset}/{annotation_type}'))])
    list_splits = sorted(os.listdir(os.path.join(root_data, f'features/{features}')))

    for split in list_splits:
        # Get a list of training video ids
        print(f'Reading splits at {os.path.join(root_data, f"annotations/{dataset}/splits/train.{split}.bundle")}')
        with open(os.path.join(root_data, f'annotations/{dataset}/splits/train.{split}.bundle')) as f:
            train_ids = [os.path.splitext(line.strip())[0] for line in f]

        list_data_files = sorted(glob.glob(os.path.join(root_data, f'features/{features}/{split}/*/*.npy')))
     
        for data_file in list_data_files:
            video_id = os.path.splitext(os.path.basename(data_file))[0]

            # load the features
            omnivore_data = load_features(data_file)
            
            # load the labels
            if video_id not in all_ids:
                # raise ValueError(f'Could not find {video_id} in annotations file"')
                # print(f'Could not find {video_id} in splits file. Skipping..."')
                # split on last _ and take the first part
                video_id = video_id.rsplit('_', 1)[0]

            #  load unique step ids
            action_classes = load_labels_raw(video_id=video_id, root_data=root_data, annotation_dataset=dataset, descriptions=False)
            label = load_labels_raw(video_id=video_id, root_data=root_data, annotation_dataset=dataset, descriptions=True)  
            assert len(label) == omnivore_data.shape[0], f'Feature-Label Length mismatch for {data_file}'

            # label = load_labels(video_id=video_id, actions=actions, root_data=root_data, annotation_dataset=dataset,
            #                 load_descriptions=load_descriptions)  
      
            # assert len(label) == omnivore_data.shape[0], f'Feature-Label Length mismatch for {data_file}: {len(label)} != {omnivore_data.shape[0]}'
                
            # Aggregate frame labels to segment labels by taking the mode
            # label, batch_idx_designation = get_segments_and_batch_idxs(label)
            batch_idx_designation = load_batch_indices(batch_idx_path, video_id)
            labels = get_segment_labels_by_batch_idxs(label, batch_idx_designation)
            action_classes = get_segment_labels_by_batch_idxs(action_classes, batch_idx_designation)
            assert len(batch_idx_designation) == omnivore_data.shape[0], f'BatchIndex-Omnivore Feature Length mismatch for {data_file}'

            # if 'fair_cooking_05_2' in video_id:
            # print(f'Video ID: {video_id} | Label Length: {len(labels)} | Feature Shape: {omnivore_data.shape}')


            batchwise_averages = []
            for batch_idx in np.unique(batch_idx_designation):
                batch_data = omnivore_data[batch_idx_designation == batch_idx]
                batch_average = np.mean(batch_data, axis=0)
                batchwise_averages.append(batch_average)
            batchwise_averages = np.array(batchwise_averages)

            # if 'fair_cooking_05_2' in video_id:
            #     print(f'Video ID: {video_id} | Label Length: {len(labels)} | Feature Shape: {batchwise_averages.shape}')

            ### REMOVE LONG TAILED CLASSES ###
            df = pd.read_csv('~/gravit/GraVi-T/data/annotations/label_mapping.csv')
            step_ids = df['step_unique_id'].values.astype(str)
            
            
            action_classes = [str(l[0]) for l in action_classes]
            assert len(action_classes) == len(labels), f'Action Classes and Labels length mismatch: {len(action_classes)} != {len(labels)}'

            # batchwise_averages = batchwise_averages[~np.isin(label, step_ids)]
            # batchwise_averages = batchwise_averages[np.isin(action_classes, step_ids)]

            keep = np.isin(action_classes, step_ids)
            # print sum of drop
            # print(f'Video ID: {video_id} | Number of segments: {len(labels)} | Number of segments to keep: {np.sum(drop)}')
            labels = [l for i, l in enumerate(labels) if keep[i]]  
            # check if all words in labels are the same
            for entry in labels:
                # check if all strings in entry are the same
                if len(set(entry)) > 1:
                    raise ValueError(f'Labels are not the same: {entry}')
                # raise ValueError(f'Labels are not the same: {labels}')


            # labels = [l for l in label if l in step_ids]
            num_segments = len(labels)
            if num_segments == 0:
                print(f'No segments left after removing long-tailed classes for {video_id}')
                continue
            ############
            # if 'cmu_bike01_2' in video_id:
            #     print(f'Video ID: {video_id} | Label Length: {len(labels)} | Feature Shape: {batchwise_averages.shape}')
            # if 'georgiatech_covid_05_10' in video_id:
            #     print(f'Video ID: {video_id} | Label Length: {len(labels)} | Feature Shape: {batchwise_averages.shape}')
            #     quit()
            # save the segment features
            if save_features:
                path = os.path.join(root_data, f'features/{output_features_dir}/{split}')
                os.makedirs(os.path.join(path, 'train'), exist_ok=True)
                os.makedirs(os.path.join(root_data, f'features/{output_features_dir}/{split}/val'), exist_ok=True)

                if video_id_label in train_ids:
                    np.save(os.path.join(path, 'train', f'{video_id}.npy'), batchwise_averages)
                else:
                    np.save(os.path.join(path, 'val', f'{video_id}.npy'), batchwise_averages)


            # save the segment labels
            if save_labels:
                save_folder = os.path.join(output_dir_path, annotation_type)
                os.makedirs(os.path.join(save_folder), exist_ok=True)
                # if os.path.exists(os.path.join(save_folder, f'{video_id}.txt')):
                #     continue
                # else:
                with open(os.path.join(save_folder, f'{video_id}.txt'), 'w') as f:
                    # if len(labels) > 1:
                    #     print(f'Length of labels is greater than 1: {len(labels)}')
                    #     print(labels[0])
                        # print(labels)
                        # raise ValueError(f'Length of labels is greater than 1: {len(labels)}')
                    for l in labels:
                        text = l[0]
                        # if annotation_type == 'groundTruth':
                        #     l = reverse[l]
                        f.write(f'{text}\n')
                        # print(l)
                print(f'Saved {video_id}.txt to {save_folder} with {len(labels)} labels')



    

            
            