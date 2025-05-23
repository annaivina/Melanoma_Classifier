import tensorflow as tf
import os
import pandas as pd 
from sklearn.utils import shuffle

class DataLoader:
    def __init__(self, dataset, csv_train, csv_test, batch_size, img_size, train_val_split=0.8, eff_net=False):

        """
        Initializes the DataLoader for the ISIC images classification task 

        Args:
            dataset (str): Root path to datasets with train/ and test/ folders 
            csv_train (str): Path to training CSV for target idintification
            csv_test (str): Path to test CSV 
            img_size (int): The image size you want to parse for resizing 260 for EffNetB2
            train_val_split (float): assign how you want to split your training set
            eff_net (bool): leave False is you train custom CNN 
            ...
        """
         

        self.dataset = dataset
        self.csv_train = csv_train
        self.csv_test = csv_test
        self.batch_size = batch_size
        self.img_size = img_size 
        self.train_val_split = train_val_split
        self.eff_net = eff_net #for efficient net we have to specifically resize image to fit 260x260 + we cant use scale (its done internally)




    def load_data(self) -> tuple[tf.data.Dataset, tf.data.Dataset, tf.data.Dataset]:

        images_train = tf.convert_to_tensor(os.path.join(self.dataset,'train/'), dtype=tf.string)
        images_test = tf.convert_to_tensor(os.path.join(self.dataset,'test/'), dtype=tf.string)

        try:
              df_train = pd.read_csv(self.csv_train)
              df_test = pd.read_csv(self.csv_test)
        except ValueError as e:
              raise("The csvs for train and test are not provided!")
              
        df_pos = df_train[df_train['target'] == 1]
        df_neg = df_train[df_train['target'] == 0]

        # Split class 1: 80% train, 20% validation
        df_pos_train = df_pos.sample(frac=self.train_val_split)
        df_pos_val = df_pos.drop(df_pos_train.index)
        
        # Do the same for class 0
        df_neg_train = df_neg.sample(frac=self.train_val_split)
        df_neg_val = df_neg.drop(df_neg_train.index)

        # Combine and shuffle each set
        df_train = shuffle(pd.concat([df_pos_train, df_neg_train], axis=0))
        df_val = shuffle(pd.concat([df_pos_val, df_neg_val], axis=0))

        X_train = df_train['image_name'].tolist()
        y_train = df_train['target'].tolist()
        
        X_val = df_val['image_name'].tolist()
        y_val = df_val['target'].tolist()

        ds_train  = tf.data.Dataset.from_tensor_slices((X_train, y_train))
        ds_valid  = tf.data.Dataset.from_tensor_slices((X_val, y_val))
   
        dataset_train = ds_train.map(lambda x, y: self.load_image(images_train, x, y, augment=True, train=True, is_eff_net=self.eff_net), num_parallel_calls=2).batch(self.batch_size).prefetch(1)
        dataset_valid = ds_valid.map(lambda x, y: self.load_image(images_train, x, y, augment=False, train=True, is_eff_net=self.eff_net), num_parallel_calls=2).batch(self.batch_size).prefetch(1)
        

        X_test = df_test['image'].tolist()
        dataset_test = tf.data.Dataset.from_tensor_slices((X_test))
        dataset_test = dataset_test.map(lambda x: self.load_image(images_test, x, augment=False, train=False, is_eff_net=self.eff_net), num_parallel_calls=2)
        dataset_test = dataset_test.shuffle(1000).batch(self.batch_size).prefetch(1)


        return dataset_train, dataset_valid, dataset_test
    
    @tf.function 
    def load_image(self, path, image_name, label=None, augment=True, train=True, is_eff_net=False):
        path = tf.convert_to_tensor(path, dtype=tf.string)
        image_name = tf.strings.join([image_name,".jpg"])
        img_path = tf.strings.join([path, image_name])
        image = tf.io.read_file(img_path)
        image = tf.image.decode_jpeg(image, channels=3)
        
        #We augment only the targets=1 (the data is very highly imbalanced) 
        if augment:
            image = tf.cond(
                tf.equal(label,1),
                lambda: self.image_augment(image),
                lambda: image #if not equal 1 return just and image
                )
            
        #Resize
        if not is_eff_net:
            image = tf.cast(image, tf.float32) / 255.0  #Dont resize for the eff net because it does internally
        
        image.set_shape([self.img_size, self.img_size, 3])
            
        return (image, label) if train else image
    
    @staticmethod
    def image_augment(image):
        image = tf.image.random_flip_left_right(image)
        image = tf.image.random_flip_up_down(image)
        image = tf.image.random_brightness(image, 0.25)
        image = tf.image.random_contrast(image, 0.6, 1.6)
        image = tf.image.rot90(image, k=1)
        image = tf.image.random_hue(image, 0.05)
        image = tf.image.transpose(image)
        image = tf.image.rot90(image, k=tf.random.uniform(shape=[], minval=0, maxval=4, dtype=tf.int32))
        image = tf.image.random_saturation(image, 0.5, 1.8)
        image = tf.image.random_jpeg_quality(image, 70, 90)
        return image
