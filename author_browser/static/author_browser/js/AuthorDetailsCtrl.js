AuthorDetailsCtrl = angular.module('pubAssistantClient').controller('AuthorDetailsCtrl', ['$scope', '$http', '$timeout', '$log',
    '$state', '$stateParams',
 function($scope, $http, $timeout, $log, $state, $stateParams) {
     $scope.id = 0;
     $scope.author = null;
     $scope.authorRequestPending = false;
     $scope.authorRequestError = false;
     $scope.articles = null;
     $scope.articlesRequestPending = false;
     $scope.articlesRequestError = false;
     $scope.coreferrers = null;
     $scope.coreferrersRequestPending = false;
     $scope.coreferrersRequestError = false;

     $scope.getAuthorInfo = function() {
        $scope.authorRequestPending = true;
        $scope.authorRequestError = false;
        $http.get(urls.authorSearchUrl, {params: {'id': $scope.id}}).then(
             function successCallback(response) {
                 $scope.authorRequestPending = false;
                 $scope.author = response.data;
             }, function failCallback(response) {
                 $scope.authorRequestPending = false;
                 $scope.authorRequestError = true;
             });
     }

     $scope.getAuthorArticles = function() {
     $scope.articlesRequestError = false;
        $scope.articlesRequestPending = true;
        $http.get(urls.authorArticlesUrl, {params: {'id': $scope.id}}).then(
             function successCallback(response) {
                 $scope.articlesRequestPending = false;
                 $scope.articles = response.data;
             }, function failCallback(response) {
                 $scope.articlesRequestPending = false;
                 $scope.articlesRequestError = true;
             });
     }

     $scope.getCoreferrers = function() {
        $scope.coreferrersRequestError = false;
        $scope.coreferrersRequestPending = true;
        $http.get(urls.authorCoreferrersUrl, {params: {'id': $scope.id}}).then(
             function successCallback(response) {
                 $scope.coreferrersRequestPending = false;
                 $scope.coreferrers = response.data;
             }, function failCallback(response) {
                 $scope.coreferrersRequestPending = false;
                 $scope.coreferrersRequestError = true;
             });
     }

     $scope.triggerReferences = function(coreferrer) {
        if (coreferrer.references.show) {
            coreferrer.references.show = false;
        } else {
            coreferrer.references.show = true;
        }
     }

     $scope.triggerBackreferences = function(coreferrer) {
        if (coreferrer.backreferences.show) {
             coreferrer.backreferences.show = false;
         } else {
             coreferrer.backreferences.show = true;
         }
     }

     if ($state.is('author-details')) {
         $scope.id = $stateParams.id;
         $scope.getAuthorInfo();
         $scope.getAuthorArticles();
         $scope.getCoreferrers();
     }
}]);