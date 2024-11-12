import os
from pyspark import SparkContext
from elasticsearch import Elasticsearch
from pyspark.sql.session import SparkSession

from clean import *
from predict import *

def addPrediction(DF, batchID, spark, impianti, modelFolder):
    finalSchema = tp.StructType([
        tp.StructField(name="carburante", dataType=tp.IntegerType(), nullable=False),
        tp.StructField(name="prezzo", dataType=tp.DoubleType(), nullable=False),
        tp.StructField(name="idImpianto", dataType=tp.IntegerType(), nullable=False),
        tp.StructField(name="Gestore", dataType=tp.StringType(), nullable=False),
        tp.StructField(name="Bandiera", dataType=tp.StringType(), nullable=False),
        tp.StructField(name="Nome Impianto", dataType=tp.StringType(), nullable=False),
        tp.StructField(name="Indirizzo", dataType=tp.StringType(), nullable=False),
        tp.StructField(name="Comune", dataType=tp.StringType(), nullable=False),
        tp.StructField(name="Latitudine", dataType=tp.FloatType(), nullable=False),
        tp.StructField(name="Longitudine", dataType=tp.FloatType(), nullable=False),
        tp.StructField(name="prediction", dataType=tp.DoubleType(), nullable=False),
    ])

    if DF.count() > 0:
        print("New batch arrived. BatchID:", batchID)
        df = DF.toPandas()
        df["prediction"] = 0.0

        assembler = VectorAssembler(inputCols=["prezzo"], outputCol="features")
        regressors = getRegressors(impianti, (batchID == 1), modelFolder=modelFolder, spark=spark, datasetFolder=os.path.join(datasetFolder, "prezzi"))
        print("Regressors READY")

        for index, row in df.iterrows():
            impianto = row["idImpianto"]
            carb = row["carburante"]
            regressor = regressors[impianto][carb]

            tempDF = spark.createDataFrame([[row["prezzo"]]], schema=tp.StructType([tp.StructField(name="prezzo", dataType=tp.FloatType(), nullable=False)]))
            tempDF = assembler.transform(tempDF)
            tempDF = regressor.transform(tempDF)

            df.at[index, "prediction"] = tempDF.collect()[0]["prediction"]

        toRet = spark.createDataFrame(df, schema=finalSchema)
        toRet = toRet.withColumn("@timestamp", fun.date_format(fun.current_timestamp(), "yyyy-MM-dd HH:mm:ss"))
        toRet = toRet.withColumn("carburante", fun.when(toRet.carburante == 0, "Benzina").otherwise("Gasolio"))
        toRet = toRet.withColumn("Location", fun.array(toRet.Longitudine, toRet.Latitudine))
        toRet = toRet.drop("Latitudine", "Longitudine")
        print("Prediction DONE")

        toRet.write \
        .option("checkpointLocation", "/save/location") \
        .option("es.nodes", ELASTIC_HOST) \
        .option("es.port", "443") \
        .option("es.resource", ELASTIC_INDEX) \
        .option("es.net.http.auth.user", ELASTIC_USER) \
        .option("es.net.http.auth.pass", ELASTIC_PASSWORD) \
        .option("es.net.ssl", "true") \
        .option("es.net.ssl.cert", "/etc/ssl/certs/ca.crt") \
        .option("es.net.ssl.cert.allow.self.signed", "false") \
        .option("es.nodes.wan.only", "true") \
        .mode("append") \
        .format("es") \
        .save()


        print("Prediction added to Elasticsearch.")
        updateDataset(df, impianti, spark, os.path.join(datasetFolder, "prezzi"))
        print("Dataset UPDATED")

def initSpark():
    sc = SparkContext(appName="OilPricePrediction")
    spark = SparkSession(sc).builder.appName("OilPricePrediction") \
        .config("spark.hadoop.fs.gs.impl", "com.google.cloud.hadoop.fs.gcs.GoogleHadoopFileSystem") \
        .config("spark.hadoop.google.cloud.auth.service.account.enable", "true") \
        .config("spark.hadoop.google.cloud.auth.service.account.json.keyfile", "/etc/gcs-key/oil-price-analyzer-28d2c0e4c729.json") \
        .config("es.net.ssl.cert", "/etc/ssl/certs/ca.crt") \
        .config("es.net.ssl", "true") \
        .getOrCreate()
    sc.setLogLevel("ERROR")

    sc.addPyFile(os.path.join(mainFolder, "clean.py"))
    sc.addPyFile(os.path.join(mainFolder, "predict.py"))
    return sc, spark

def createElasticIndex(host, index, mapping):
    es = Elasticsearch(hosts=[host], http_auth=(ELASTIC_USER, ELASTIC_PASSWORD))

    if es.indices.exists(index=index):
        print(f"Index {index} already exists. Skipping creation.")
    else:
        response = es.indices.create(index=index, body=mapping, ignore=400)
        if response.get('acknowledged'):
            print(f"Index created successfully: {index}")
        else:
            print(f"Error creating index {index}: {response}")
    return es

def main(spark):
    inputDF = spark.readStream.format("kafka") \
            .option("kafka.bootstrap.servers", KAFKA_SERVER) \
            .option("subscribe", KAFKA_TOPIC) \
            .load()

    df = cleanStreamingDF(inputDF, anagrafica)

    df.writeStream \
        .foreachBatch(lambda df, batchId: addPrediction(df, batchId, spark, impianti, modelFolder)) \
        .start() \
        .awaitTermination()

if __name__ == "__main__":
    KAFKA_TOPIC = "prices"
    KAFKA_SERVER = "kafkaServer:9092"
    ELASTIC_HOST = "https://0595b857a92b432692ac00a0edaf3cad.us-central1.gcp.cloud.es.io"
    ELASTIC_USER = "elastic"
    ELASTIC_PASSWORD = "bEFTVBGMlJ22QSlDAvB9boT2"
    ELASTIC_INDEX = "prices"

    ES_MAPPING = {
        "mappings": {
            "properties": {
                "idImpianto": {"type": "keyword"},
                "carburante": {"type": "keyword"},
                "prezzo": {"type": "float"},
                "@timestamp": {"type": "date", "format": "yyyy-MM-dd HH:mm:ss"},
                "prediction": {"type": "float"},
                "Gestore": {"type": "text"},
                "Bandiera": {"type": "keyword"},
                "Nome Impianto": {"type": "text"},
                "Indirizzo": {"type": "text"},
                "Comune": {"type": "keyword"},
                "Location": {"type": "geo_point"},
            },
        },
    }

    mainFolder = os.path.dirname(os.path.realpath(__file__))
    # modelFolder = os.path.join(mainFolder, "model")
    # modelFolder = os.path.join("tmp", "model")
    modelFolder = "/tmp/model"
    # datasetFolder = os.path.join(mainFolder, "dataset")
    datasetFolder = "gs://oil-price-analyzer"
    
    sc, spark = initSpark()
    es = createElasticIndex(ELASTIC_HOST, ELASTIC_INDEX, ES_MAPPING)
    spark.conf.set("spark.sql.execution.arrow.pyspark.enabled", "true")

    anagrafica = spark.read.parquet("anagrafica_impianti_CT.parquet")
    impianti = [x.idImpianto for x in anagrafica.select("idImpianto").distinct().collect()]
    
    main(spark)
