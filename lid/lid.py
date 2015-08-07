from __future__ import division


'''main module for the LID (legislative influence detector) system '''
from config import DATA_PATH
from database import ElasticConnection
from multiprocessing import Pool
from text_alignment import LocalAligner
from utils.text_cleaning import clean_document
from utils.utils import alignment_tokenizer
import argparse
import json
import logging
import os
import re
import time
import traceback


class LID(object):
    '''LID class that contains all of the central functionality for querying and aligning text between state
    bills and model legistlation'''

    
    def __init__(self,aligner = LocalAligner(),elastic_host = "localhost",elastic_port=9200,
            query_results_limit=100,score_threshold = 0.5):
        '''
        alignment_object: any object that inherets from abstract class Alignment

        elastic_host: ip adress of the elastic search instance (default: localhost)

        elastic_port: port of the elastic search instance (defualt: 9200)

        num_results_limit: the limit on the number of results to return with the elastic search query (default: 100)
        
        '''
        self.aligner = aligner
        self.elastic_connection = ElasticConnection(host = elastic_host,port = elastic_port)
        self.results_limit = query_results_limit
        self.score_threshold = score_threshold
        
    

    def find_alignments(self,query_document,document_type = "text",split_sections = False,**kwargs):
        '''
        query_document: query document, usually in the form of an entire bill, model legistlation or segment of either
        
        document_type: specifies the document type, default: "text" means that know section chunking will be done
                        on the query, other options include state bill tuples i.e ("state_bill","al")
                        and "model_legistlation"

        split_sections: specifies whether the query document will be broken into sections to find multiple alignments
                        (True) or whether to treat the documents as one and identify a single best alignment (False)
                            
        '''
        query_document = clean_document(query_document,doc_type = document_type,
                    split_to_section = split_sections, **kwargs)

        if type(query_document) == list:
            elastic_query = u" ".join(query_document)
        else:
            elastic_query = query_document
        

        #query elastic search
        result_docs = self.elastic_connection.similar_doc_query(elastic_query,num_results = self.results_limit,
                return_fields = ["state","bill_document_last"])

        #run alignment algorithm
        if split_sections == True:
            align_doc = [alignment_tokenizer(s) for s in query_document]
        else:
            align_doc = alignment_tokenizer(query_document)
        
        t_align = 0    
        num_states = 0
        alignment_docs = []
        for i,res_doc in enumerate(result_docs):
            if res_doc['score'] < 0.5:
                break
            if res_doc['state'] == kwargs['state_id']:
                print res_doc['state']
                num_states+=1
            print res_doc['score']
            res_sequence = clean_document(res_doc['bill_document_last'],state_id = res_doc['state'])
            res_sequence = alignment_tokenizer(res_sequence)
            
            if split_sections == True:
                alignment = self.aligner.align_by_section(align_doc,res_sequence)
            else:
                alignment = self.aligner.align(align_doc,res_sequence)

            alignment_docs.append(alignment)
        
        print "num_states",num_states
        return alignment_docs







#Below are functions that use lid objects to identify similar bills/model legislation in the dataset,
#will be moved to another module in the next version

##helper function for process for precompute_bill_similarity
def retrieve_similar_bills(bill_id):
    try:
        ec = database.ElasticConnection()
        bill_doc = ec.get_bill_by_id(bill_id)
        
        bill_text,state = (bill_doc['bill_document_last'],bill_doc['state'])
        
        logging.info("successfully obtained similar docs for {0}".format(bill_id))
        if bill_text is None:
            result_ids = []
        else:
            bill_text = clean_text_for_query(bill_text,state)
            result_docs = ec.similar_doc_query(bill_text,num_results = 10)
            result_ids = [{"id":r['id'],"score":r['score'],"state":r['state']} for r in result_docs]
        
        del ec
        del bill_text
        del state
        return (bill_id,result_ids)
            
    except (KeyboardInterrupt, SystemExit):
        raise
    except:
        trace_message = re.sub("\n+", "\t", traceback.format_exc())
        trace_message = re.sub("\s+", " ", trace_message)
        trace_message = "<<{0}>>".format(trace_message)
        m = "Failed to obtain similar docs for {0}: {1}".format(bill_id, trace_message)
        logging.error(m)
        return (bill_id,[])
        
def precompute_bill_similarity(ec):
    """uses elasticsearch queries to find all bill pairs for which there is a potential alignment"""
    
    bill_ids = [x.strip() for x in open("{0}/data/bill_ids.txt".format(os.environ['POLICY_DIFFUSION']))]

    pool = Pool(processes = 7)
    results = pool.map(retrieve_similar_bills,bill_ids)

    return results

def main():
    parser = argparse.ArgumentParser(description='runs scripts for lid system')
    parser.add_argument('command', help='command to run, options are: build_index')
    parser.add_argument('--data_path', dest='data_path', help="file path of data to be indexed ")

    args = parser.parse_args()
    if args.command == "compute_bill_similarity_matrix":
        #handle error logger
        logging.basicConfig(filename="{0}/logs/bill_similarity_matrix.log".format(os.environ['POLICY_DIFFUSION']),
                level=logging.DEBUG)
        logging.getLogger('elasticsearch').setLevel(logging.ERROR)
        logging.getLogger('urllib3').setLevel(logging.ERROR)
        
        out_file = open("{0}/bill_similarity_matrix.json".format(DATA_PATH),'w')
        
        bill_ids = [x.strip() for x in open("{0}/data/bill_ids.txt".format(os.environ['POLICY_DIFFUSION']))]

        pool = Pool(processes = 7)
        results = pool.map(retrieve_similar_bills,bill_ids)
        
        json_obj = {}
        for doc_id,sim_docs in results:
            json_obj[doc_id] = sim_docs
        out_file.write(json.dumps(json_obj))
    

if __name__ == "__main__":
    main()