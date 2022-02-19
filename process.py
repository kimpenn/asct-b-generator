#!/usr/bin/python3

'''
- include "notes" and "ABBR" (abbreviation) fields for each feature
- need better demo and more clear instructions. Use color coding in demo and documentation.
- use a real world demo, perhaps defining a family tree.
- label = Uberon RDFS label
- "input table" is the input file for the Generator
- note in docs that revisions need to happen to the input table, not the ASCT+B table
- expect 10 row header and duplicate into output
'''

'''
Requires anytree:
https://pypi.org/project/anytree/

Assumptions:

  1. Inner nodes can contain biomarkers or references, not just leaves
  and cell types.

  2. All anatomical structures must be uniquely named, for example,
     there can not be two structures called "ovary" but there can be
     "left ovary" and "right ovary".

  3. Cell type is only one level; that is, cell types can not have
  child cell types.

  4. Commas can not be used in names for anatomical structures, cells,
  or features.
'''

import sys
import re
import argparse
from anytree import Node, SymlinkNode, RenderTree, AsciiStyle, LevelOrderGroupIter, Walker
from anytree.exporter import DotExporter


################################################
# Globals

DEBUG = False

# number of columns in the input file
INPUT_COLUMNS = 15

# print the tree to the command line
print_tree = False

# requiring each anatomical structure to have one and only one
# parent. When true, if the same sub-structure exists in multiple
# parent-structures, then each child structure would need to be
# uniquely named.
only_on_parent = False

# if true, we will automatically generate missing cells, biomarkers
# and references. The generated ones will contain no secondary
# details. Anatomical structures must be defined.
missing_feature_ok = False

# all anatomical structures
nodes = {}

# the top level node
tree_root = ""

# all cells, biomarkers and references
features = {}

# compute these based on the max number of biomarkers across nodes and
# cells
max_genes = 0
max_proteins = 0
max_proteoforms = 0
max_lipids = 0
max_metabolites = 0
max_ftu = 0
# we don't actually need to track the max level for references as it's
# last data block, however, this is a hack to allow us to handle
# references like the biomarkers.
max_references = 0

# the file handles
in_file = ""
out_file = ""
dot_file = None


################################################
# Classes

class Feature:
    """
    used to store cells as well as biomarkers and references
    """
    
    def __init__(self, name, feature_type, label="", id="", note="", abbr="", **kwargs):
        self.name = name
        self.feature_type = feature_type
        self.label = label
        self.id = id
        self.note = note
        self.abbr = abbr
        self.genes = kwargs.get('genes', None)
        self.proteins = kwargs.get('proteins', None)
        self.proteoforms = kwargs.get('proteoforms', None)
        self.lipids = kwargs.get('lipids', None)
        self.metabolites = kwargs.get('metabolites', None)
        self.ftu = kwargs.get('ftu', None)
        self.references = kwargs.get('references', None)

    def __str__(self):
        out = "[" + self.name
        out += " type:" + self.feature_type
        if self.genes:
            out += " genes:" + str(self.genes)
        out += "]"
        return out


################################################
# Functions

def no_features(node):
    """
    Check if a node contains any cells or features.
    """

    # check for all biomarkers and references
    if node.cells or node.genes or node.proteins or node.proteoforms or node.lipids or node.metabolites or node.ftu or node.references:
        return False
    return True


def get_header_block(content, depth):
    """
    generates the five column headers as exemplified below:
    AS/1	AS/1/LABEL	AS/1/ID	AS/1/NOTE	AS/1/ABBR
    """
    output = content + "/" + str(depth) + "\t"
    output += content + "/" + str(depth) + "/LABEL\t"
    output += content + "/" + str(depth) + "/ID\t"
    output += content + "/" + str(depth) + "/NOTE\t"
    output += content + "/" + str(depth) + "/ABBR"
    return output


def get_biomarker_header(biomarker, max_depth):
    output = ""
    for depth in range(1, max_depth+1):
        output += get_header_block(biomarker, depth) + "\t"
    return output

def print_ASCTB_header(max_AS_depth):
    global max_genes, out_file

    header = ""

    # add anatomical structures
    for depth in range(1, max_AS_depth+1):
        header += get_header_block("AS", depth) + "\t"

    # assume cell type is only one depth
    header += get_header_block("CT", 1) + "\t"

    # add biomarkers
    header += get_biomarker_header("BGene", max_genes)
    header += get_biomarker_header("BProteins", max_proteins)
    header += get_biomarker_header("BProteoforms", max_proteoforms)
    header += get_biomarker_header("BLipids", max_lipids)
    header += get_biomarker_header("BMetabolites", max_metabolites)
    header += get_biomarker_header("FTU", max_ftu)

    # we handle references separately because their header details
    # differ from the biomarkers.
    for depth in range(1, max_references+1):
        header += "REF/" + str(depth) + "\t" + "REF/" + str(depth) + "/DOI\t" + "REF/" + str(depth) + "/NOTES"
        # prevent a tab at the end of the header line
        if depth < max_references:
            header += "\t"
    
    header += "\n"
    out_file.write(header)


def get_data_block(feature):
    """
    Generates a triplet for a feature
    """
    return feature.name + "\t" + feature.label + "\t" + feature.id + "\t" + feature.note + "\t" + feature.abbr


def add_biomarkers(elements, max_depth):
    """
    Outputs the biomarker data and/or tabs as appropriate
    """
    global features, missing_feature_ok
    
    output = ""
    count = 0
    if elements:
        for element in elements:
            if element not in features:
                # TEST: feature isn't defined
                if missing_feature_ok:
                    # add a place holder cell type
                    features[element] = Feature(element, "", label="", id="", note="", abbr="")
                else:
                    error = "ERROR: feature hasn't been defined. Please add a row to the input that defines this feature."
                    error += "\n\tFeature: " + element
                    exit_with_error(error)
            output += get_data_block(features[element]) + "\t"
            count += 1
    if count < max_depth:
        output += "\t\t\t\t\t" * (max_depth-count)
    return output


def add_features(record, element):
    """
    The argument (element) can be either an anatomical structure ("node")
    or a cell as they contain the same features.
    """
    global features, out_file

    # need to track how many entities we output per feature type, to
    # appropriately pad the output.
    count = 0

    # add biomarkers
    record += add_biomarkers(element.genes, max_genes)
    record += add_biomarkers(element.proteins, max_proteins)
    record += add_biomarkers(element.proteoforms, max_proteoforms)
    record += add_biomarkers(element.lipids, max_lipids)
    record += add_biomarkers(element.metabolites, max_metabolites)
    record += add_biomarkers(element.ftu, max_ftu)
    record += add_biomarkers(element.references, max_references)

    record += "\n"
    out_file.write(record)


def print_ASCTB_table():
    """
    Print the ASCT+B table, stepping through the tree, one level at a
    time and applying each of the relevant cells and features to the
    node.
    """
    global nodes, tree_root, features, missing_feature_ok

    # get a list of lists where the sub-lists are the nodes per level
    # of the tree. The list returned will appropriately include
    # Symlink'ed Nodes but it won't actually reference the Symlink but
    # rather the original Node. So we need to manually process the
    # Symlinks, when we've seen a Node more than once.
    levels = [[node.name for node in children] for children in LevelOrderGroupIter(tree_root)]

    # total number of anatomical structure levels
    max_AS_depth = len(levels)

    print_ASCTB_header(max_AS_depth)

    # we need to track which AS level we're at, so we can pad as
    # needed when we add cells.
    AS_depth = 0
    w = Walker()
    for level in levels:
        AS_depth += 1
        for node_name in level:
            node = nodes[node_name]

            # if we've already processed this node once, then we need
            # to use one of the Symlinks. LevelOrderGroupIter() only
            # returns the original Node in place of each of the
            # Symlinks.
            if node.processed > 0:
                node = node.symlinks[node.processed-1]
            node.processed += 1
            
            # if inner node and doesn't have any features, then skip
            # to the next node.
            if no_features(node) and not node.is_leaf:
                continue

            # walk the tree up from the node to the root. The first
            # tuple is for upward walking and the second is just the
            # tree root. So we only care about the third tuple which
            # is the downward walking.
            walked = w.walk(tree_root, node)[2]
            # add root, since it was in the middle tuple that we
            # ignore.
            walked = (tree_root,) + walked

            # add all ancestral anatomical structures to the data
            # record being output.
            anatomical_structure = ""
            for ancestor in walked:
                anatomical_structure += get_data_block(ancestor) + "\t"

            # pad record, to account for structures that aren't as
            # deep as the maximum possible depth (max_AS_depth).
            anatomical_structure += "\t\t\t\t\t" * (max_AS_depth - AS_depth)

            # track if we've printed the node in some form
            node_output = False

            # add cell-independent features here
            if node.genes or node.proteins or node.proteoforms or node.lipids or node.metabolites or node.ftu or node.references:
                # skip the cell block
                record = anatomical_structure + "\t\t\t\t\t"
                # add features
                add_features(record, node)
                node_output = True

            # add cells and cell-dependent features
            cells = node.cells
            if cells:
                for cell in cells:
                    if cell not in features:
                        # TEST: cell isn't defined
                        if missing_feature_ok:
                            # add a place holder cell type
                            features[cell] = Feature(cell, "CT", label="", id="", note="", abbr="")
                        else:
                            error = "ERROR: cell hasn't been defined. Please add a row to the input that defines this cell."
                            error += "\n\tCell: " + cell
                            error += "\n\tAnatomical Structure: " + node.name
                            exit_with_error(error)

                    cell_feature = features[cell]
                    record = anatomical_structure + get_data_block(cell_feature) + "\t"

                    # add cell-specific features
                    add_features(record, cell_feature)
                    node_output = True

            # if node is leaf and doesn't have any assigned cells or
            # features then we output it here.
            if not node_output:
                record = anatomical_structure + "\t\t\t\t\t" * (1 + max_genes + max_proteins + max_proteoforms + max_lipids + max_metabolites + max_ftu + max_references) + "\n"
                out_file.write(record)

                    
def close_files():
    """
    Prepare to quit
    """
    global in_file, out_file

    in_file.close()
    out_file.close()
    if dot_file:
        dot_file.close()


def exit_with_error(error):
    """
    Quit with an error
    """
    close_files()
    sys.exit(error)


def process_input(input_string, max_depth):
    """
    Clean up the input, convert it to an array and compute the longest
    array, per feature type.
    """

    # remove the quotes and extra spaces from the input string
    input_string = input_string.replace('"', '').replace(', ', ',').strip()

    # convert the string to an array and also track the longest array, so
    # we know how many levels for the feature type.
    tmp = []
    if input_string:
        tmp = input_string.split(',')
        if max_depth < len(tmp):
            max_depth = len(tmp)

    # return the array and the depth
    return tmp, max_depth


def build_tree(nodes_to_process, dup_nodes):
    global nodes, only_one_parent
    
    for node in nodes_to_process:
        children = nodes[node].kids
        if children:
            for child in children:
                if child not in nodes:
                    error = "ERROR: anatomical structure hasn't been defined. Please add a row to the input that defines this structure."
                    error += "\n\tStructure: " + child
                    error += "\n\tParent: " + node                    
                    exit_with_error(error)
                    
                child_node = nodes[child]
                if child_node.parent:
                    # TEST: a node has more than one parent
                    if only_one_parent:
                        error = "ERROR: anatomical structure has two parents."
                        error += "\n\tStructure: " + child
                        error += "\n\tParent: " + child_node.parent.name
                        error += "\n\tParent: " + node
                        exit_with_error(error)

                    # child already has a parent, so need to create a
                    # duplicate (Symlink) child, to allow for multiple
                    # parents. 
                    new_child = SymlinkNode(child_node, parent=nodes[node])
                    dup_nodes[new_child] = new_child
                    
                    # We need to track duplicates because
                    # LevelOrderGroupIter() doesn't differentiate
                    # between a Node and a Symlink. Hence when we
                    # export the tree Symlinks get lost.
                    if child_node.symlinks:
                        child_node.symlinks.append(new_child)
                    else:
                        child_node.symlinks = [new_child]
                else:
                    child_node.parent = nodes[node]
                    
    return dup_nodes


def process_arguments():
    global in_file, out_file, dot_file, print_tree, only_one_parent, missing_feature_ok
    """
    Handle command line arguments.
    """
    
    parser = argparse.ArgumentParser(description="Generate ASCT+B table.")
    parser.add_argument("-m", "--missing", help="Ignore missing cell types, biomarkers and references. For example, if a cell type is marked as containing a biomarker that wasn't defined, this flag would prevent the program from exiting with an error and instead the ASCT+B table would be generated. When the flag isn't used, all features must be defined.", action="store_true")
    parser.add_argument("-u", "--unique", help="Make sure all anatomical structures have one and only one parent.", action="store_true")
    parser.add_argument("-d", "--dot", help="Output tree as a DOT file for plotting with Graphviz.", action="store_true")
    parser.add_argument("-v", "--verbose", help="Print the tree to the terminal.", action="store_true")
    parser.add_argument("input", type=str, help="Input file")
    parser.add_argument("output", type=str, help="Output file (TSV)")

    args = parser.parse_args()
    
    # open input file.
    in_file = open(args.input, "r")

    # this will overwrite any existing file
    out_file = open(args.output, "w")

    if args.dot:
        dot_file = open(args.output + ".dot", "w")

    print_tree = args.verbose
    only_one_parent = args.unique
    missing_feature_ok = args.missing


################################################
# Main

# Cxecute script
if __name__ == "__main__":

    process_arguments()

    contents = in_file.readlines()
    headerLine = True
    for line in contents:
        # parse the tab-delimited line
        line_as_list = re.split(r'\t', line.rstrip('\n'))
        # make sure the line contains the appropriate number of fields
        if len(line_as_list) != INPUT_COLUMNS:
            error = "ERROR: incorrect number of fields in line. The tab-delimited line should contain " + INPUT_COLUMNS + "  fields: "
            error += "\n\tname, label, ID, node, abbreviation, feature type, children, cells, genes, proteins, proteoforms, lipids, metabolites, FTU, references"
            error += "\n\tNumber of fields found in line: " + str(len(line_as_list))
            error += "\n\tLine: " + line
            exit_with_error(error)
        name, label, id, note, abbr, feature_type, children_string, cells_string, genes_string, proteins_string, proteoforms_string, lipids_string, metabolites_string, ftu_string, references_string = line_as_list

        # the first line is a header line, which we skip here
        if headerLine:
            headerLine = False
            continue

        # clean up white spaces
        name = name.strip()

        # TEST: make sure names don't contain commas
        if name.find(',') > -1:
            error = "ERROR: names can not include commas (',')."
            error += "\n\tName: " + name
            exit_with_error(error)

        # convert strings into lists and get the number of levels per
        # feature type
        children_string = children_string.replace('"', '').replace(', ', ',').strip()
        children = []
        if len(children_string) > 0:
            children = children_string.split(',')
        cells_string = cells_string.replace('"', '').replace(', ', ',').strip()
        cells = []
        if len(cells_string) > 0:
            cells = cells_string.split(',')
        genes, max_genes = process_input(genes_string, max_genes)
        proteins, max_proteins = process_input(proteins_string, max_proteins)
        proteoforms, max_proteoforms = process_input(proteoforms_string, max_proteoforms)
        lipids, max_lipids = process_input(lipids_string, max_lipids)
        metabolites, max_metabolites = process_input(metabolites_string, max_metabolites)
        ftu, max_ftu = process_input(ftu_string, max_ftu)
        references, max_references = process_input(references_string, max_references)

        '''
        # TEST: make sure biomarkers and references are only applied to leaves or cell types
        if (feature_type == "AS") and children and (genes, lipids...):
            error = "ERROR: biomarkers and references can only be applied to anatomical structures without children or to cell types."
            error += "\n\tStructure: " + name
            error += "\n\tChildren: " + str(children)
            error += "\n\tCells: " + str(cells)
            error += "\n\tGenes: " + str(genes)
            exit_with_error(error)
        '''
        
        # TEST: check that biomarkers and references are only applied to AS and CT.
        if (feature_type not in ("AS", "CT")) and (genes or proteins or proteoforms or lipids or metabolites or ftu or references):
            error = "ERROR: biomarkers and references can only be applied to anatomical structures or cell types."
            error += "\n\tEntity: " + name
            error += "\n\tLabel: " + label
            error += "\n\tID: " + id
            error += "\n\tnote: " + note
            error += "\n\tABBR: " + abbr
            error += "\n\tChildren: " + str(children)
            error += "\n\tCells: " + str(cells)
            error += "\n\tGenes: " + str(genes)
            error += "\n\tProteins: " + str(proteins)
            error += "\n\tProteoforms: " + str(proteoforms)
            error += "\n\tLipids: " + str(lipids)
            error += "\n\tMetabolites: " + str(metabolites)
            error += "\n\tFTU: " + str(ftu)
            error += "\n\tReferences: " + str(references)
            exit_with_error(error)

        # add record to the node or feature dictionaries
        if feature_type == "AS":
            # "children" is a reserved word in Node() and here we want
            # to store the string of children, so we use "kids"
            node = Node(name, label=label, id=id, note=note, abbr=abbr, kids=children, cells=cells, genes=genes, proteins=proteins, proteoforms=proteoforms, lipids=lipids, metabolites=metabolites, ftu=ftu, references=references, symlinks=None, processed=0)

            if name in nodes:
                # TEST: anatomical structures' name already used
                error = "ERROR: two anatomical structures can not have the same name. However, by default, a single anatomical structure can be the child of multiple parents."
                error += "\n\t" + str(node)
                error += "\n\t" + str(nodes[name])
                exit_with_error(error)
            else:
                nodes[name] = node
        else:
            # Feature class is used to store both cells and biomarkers.
            feature = Feature(name, feature_type, label=label, id=id, note=note, abbr=abbr, genes=genes, proteins=proteins, proteoforms=proteoforms, lipids=lipids, metabolites=metabolites, ftu=ftu, references=references)
            if name in features:
                # TEST: feature name already used
                error = "ERROR: all features must have a unique name."
                error += "\n\t" + str(feature)
                error += "\n\t" + str(features[name])
                exit_with_error(error)
            else:
                features[name] = feature

    # everything loaded, so now build the tree, allowing for duplicate nodes
    dup_nodes = build_tree(nodes, {})
    # add duplicate nodes to our global node dictionary
    nodes.update(dup_nodes)

    # keep running build_tree() until all duplicate nodes have been
    # processed as each run of build_tree() might generate more
    # duplicate nodes needing to be processed.
    while dup_nodes:
        dup_nodes = build_tree(dup_nodes, {})
        nodes.update(dup_nodes)

    # set tree_root to the root of the tree
    for node in nodes:
        if nodes[node].is_root:
            if tree_root:
                # TEST: more than one node without a parent (ie., "root").
                error = "ERROR: anatomical structure(s) lacking parents."
                error += "\n\tStructure: " + tree_root.name
                error += "\n\tStructure: " + node
                exit_with_error(error)
            tree_root = nodes[node]

    # print the ASCT+B table
    print_ASCTB_table()

    if DEBUG:
        # Height returns the number of edges, but we want the number of node levels.
        print("Anatomical structure levels: ", tree_root.height+1)
        # print each of the levels.
        print([[node.name for node in children] for children in LevelOrderGroupIter(tree_root)])

        # print tree with all details
        print("\n", RenderTree(tree_root))

        print("\nNodes:")
        for node in nodes:
            if nodes[node].parent:
                print(node, nodes[node].parent.name)

        print("\nFeatures:")
        for feature in features:
            print(features[feature])

    if print_tree:
        print("\n", RenderTree(tree_root, style=AsciiStyle()).by_attr())

    if dot_file:
        for line in DotExporter(tree_root):
            dot_file.write(line)

    close_files()
