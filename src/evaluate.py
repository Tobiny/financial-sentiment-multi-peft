import os
import sys
import torch
from torch.utils.data import DataLoader, TensorDataset
from transformers import BertTokenizer
from peft import PeftModel, PeftConfig
from data_preparation import load_data, preprocess_data, split_data, create_text_representation
from model_utils import evaluate_model, load_bert_model, plot_confusion_matrix
import logging
from datetime import datetime


def setup_logging():
    log_dir = '../logs'
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f'evaluation_log_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt')

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] - %(message)s',
        handlers=[
            logging.FileHandler(log_file, mode='w'),
            logging.StreamHandler(sys.stdout)
        ]
    )

    if os.path.exists(log_file):
        print(f"Log file created: {log_file}")
    else:
        print(f"Failed to create log file: {log_file}")

    return logging.getLogger(__name__)


def load_peft_model(base_model_name, peft_model_path):
    from transformers import AutoModelForSequenceClassification

    config = PeftConfig.from_pretrained(peft_model_path)
    base_model = AutoModelForSequenceClassification.from_pretrained(base_model_name)
    model = PeftModel.from_pretrained(base_model, peft_model_path)
    return model


def main():
    logger = setup_logging()
    logger.info("Evaluation started")

    logger.info("Loading and preprocessing data...")
    df = load_data('../data/heart_2022_no_nans.csv')
    X, y = preprocess_data(df)
    _, X_test, _, y_test = split_data(X, y)

    logger.info("Creating text representations...")
    X_test_text = create_text_representation(X_test)

    logger.info("Loading BERT tokenizer...")
    tokenizer = BertTokenizer.from_pretrained("bert-base-uncased")

    logger.info("Tokenizing data...")
    test_encodings = tokenizer(X_test_text, truncation=True, padding=True, max_length=512)

    logger.info("Creating dataset...")
    test_dataset = TensorDataset(
        torch.tensor(test_encodings['input_ids']),
        torch.tensor(test_encodings['attention_mask']),
        torch.tensor(y_test.values)
    )

    logger.info("Creating dataloader...")
    test_dataloader = DataLoader(test_dataset, batch_size=16)

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    logger.info(f"Using device: {device}")

    logger.info("\nEvaluating base BERT model:")
    _, base_model = load_bert_model()
    base_model = base_model.from_pretrained("../saved_models/bert_model")
    base_model.to(device)
    base_model.eval()

    logger.info("\nEvaluating PEFT model:")
    peft_model = load_peft_model("bert-base-uncased", "../saved_models/peft_model")
    peft_model.to(device)
    peft_model.eval()

    models = [("Base BERT", base_model), ("PEFT BERT", peft_model)]

    for model_name, model in models:
        logger.info(f"\nEvaluating {model_name}:")
        all_preds = []
        all_labels = []

        with torch.no_grad():
            for batch in test_dataloader:
                batch = tuple(t.to(device) for t in batch)
                inputs = {'input_ids': batch[0], 'attention_mask': batch[1]}
                labels = batch[2]

                outputs = model(**inputs)
                logits = outputs.logits
                preds = torch.argmax(logits, dim=1)

                all_preds.extend(preds.cpu().numpy())
                all_labels.extend(labels.cpu().numpy())

        metrics, cm = evaluate_model(all_labels, all_preds)
        plot_confusion_matrix(cm, ['No Heart Attack', 'Heart Attack'])

        logger.info(f"{model_name} performance:")
        for metric, value in metrics.items():
            logger.info(f"{metric}: {value:.4f}")

    logger.info("Evaluation complete.")


if __name__ == "__main__":
    main()