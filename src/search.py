"""Pose une question à l'index et affiche les 5 fiches les plus proches.

    python src/search.py "Can we detect emotions of employees?"
    python src/search.py "هل يمكن التعرف على مشاعر الموظفين؟" --model e5-large
    python src/search.py "..." --lang fr      → ne cherche que dans les fiches françaises
"""
import argparse

from embeddings import encode, get_collection, load_model


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("question")
    parser.add_argument("--model", default="bge-m3")
    parser.add_argument("--lang", default=None, help="en ou fr ; par défaut les deux")
    parser.add_argument("-k", type=int, default=5, help="nombre de fiches à afficher")
    args = parser.parse_args()

    model = load_model(args.model)
    query_vector = encode(model, args.model, [args.question], kind="query")

    collection = get_collection(args.model)
    results = collection.query(
        query_embeddings=query_vector,
        n_results=args.k,
        where={"lang": args.lang} if args.lang else None,  # filtre par métadonnée
    )

    print(f"\nQuestion : {args.question}   (modèle : {args.model})\n")
    for rank, (chunk_id, distance, text) in enumerate(
        zip(results["ids"][0], results["distances"][0], results["documents"][0]), start=1
    ):
        similarity = 1 - distance  # ChromaDB renvoie une distance ; on la retransforme en cosinus
        print(f"{rank}. {chunk_id:<22} cosinus = {similarity:.3f}")
        print(f"   {text[:160]}...\n")


if __name__ == "__main__":
    main()
